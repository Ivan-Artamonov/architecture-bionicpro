import json
import os
import re
import threading
import time
from datetime import date

import boto3
import httpx
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response

app = FastAPI()
SOURCE = os.getenv('REPORT_SOURCE', 'cdc')
if SOURCE not in ('etl', 'cdc'):
    raise RuntimeError('REPORT_SOURCE должен быть etl или cdc')
TABLE = f'reports_{SOURCE}'
KEY = os.getenv('INTERNAL_KEY', 'local-internal-key')
BUCKET = 'reports'
http = httpx.Client(timeout=15)
s3 = boto3.client('s3', endpoint_url=os.getenv('S3_URL', 'http://minio:9000'),
                  aws_access_key_id=os.getenv('S3_USER', 'minioadmin'),
                  aws_secret_access_key=os.getenv('S3_PASSWORD', 'minioadmin-local'),
                  region_name='us-east-1')
metadata = None
metadata_until = 0
lock = threading.Lock()


def internal(value):
    if value != KEY:
        raise HTTPException(403)


def query(sql, **params):
    response = http.post(os.getenv('CLICKHOUSE_URL', 'http://clickhouse:8123'),
                         params={'database': 'bionic', **{f'param_{k}': str(v) for k, v in params.items()}},
                         auth=(os.getenv('CLICKHOUSE_USER', 'bionic'),
                               os.getenv('CLICKHOUSE_PASSWORD', 'local-clickhouse')),
                         content=sql + ' FORMAT JSONEachRow')
    response.raise_for_status()
    return [json.loads(line) for line in response.text.splitlines() if line]


def publication():
    global metadata, metadata_until
    with lock:
        if metadata is None or time.time() >= metadata_until:
            rows = query(f"SELECT generation, processed_until FROM {TABLE} WHERE subject = '' LIMIT 1")
            if not rows or rows[0]['processed_until'] <= '1970-01-01':
                raise HTTPException(409, 'Данные ещё не обработаны. Запустите DAG и дождитесь витрины')
            metadata, metadata_until = rows[0], time.time() + 15
        return metadata.copy()


def exists(key):
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except ClientError as error:
        if error.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound'):
            return False
        raise


@app.get('/health')
def health():
    return {'status': 'ok', 'source': SOURCE}


@app.get('/reports')
def reports(start: date, end: date, x_user_id: str = Header(), x_internal_key: str = Header()):
    internal(x_internal_key)
    # LDAP subject может иметь вид f:component-id:entryUUID, а локальный — UUID.
    if not re.fullmatch(r'[a-zA-Z0-9:._-]{1,160}', x_user_id):
        raise HTTPException(400, 'Некорректный идентификатор')
    if not start < end or (end - start).days > 31:
        raise HTTPException(400, 'Период должен составлять от 1 до 31 дня; end не включается')
    try:
        meta = publication()
        if end > date.fromisoformat(meta['processed_until']):
            raise HTTPException(409, {'message': 'Этот период ещё не обработан',
                                      'processed_until': meta['processed_until']})
        generation = str(meta['generation'])
        key = f'reports/{SOURCE}/{generation}/{x_user_id}/{start}_{end}.json'
        cached = exists(key)
        if not cached:
            rows = query(f'''SELECT report_date, client_name, device_count, samples,
                                    avg_response_ms, max_response_ms, recognized_pct, min_battery
                             FROM {TABLE}
                             WHERE subject = {{subject:String}}
                               AND generation = {{generation:UInt64}}
                               AND report_date >= {{start:Date}} AND report_date < {{end:Date}}
                             ORDER BY report_date''', subject=x_user_id, generation=generation,
                         start=start, end=end)
            if not rows:
                # Витрина могла смениться между чтением версии и строк.
                global metadata_until
                metadata_until = 0
                fresh = publication()
                if str(fresh['generation']) != generation:
                    raise HTTPException(409, 'Витрина обновилась. Повторите запрос')
                raise HTTPException(404, 'За этот период нет данных о ваших протезах')
            report = {'subject': x_user_id, 'start': str(start), 'end_exclusive': str(end),
                      'source': SOURCE, 'generation': generation,
                      'processed_until': meta['processed_until'], 'days': rows}
            s3.put_object(Bucket=BUCKET, Key=key,
                          Body=json.dumps(report, ensure_ascii=False).encode(),
                          ContentType='application/json; charset=utf-8')
        return {'url': f'/cdn/{key}', 'cached': cached,
                'processed_until': meta['processed_until']}
    except HTTPException:
        raise
    except (httpx.HTTPError, ClientError):
        raise HTTPException(503, 'Хранилище отчётов временно недоступно')


@app.get('/internal/objects/{key:path}')
def get_object(key: str, x_internal_key: str = Header()):
    internal(x_internal_key)
    if not re.fullmatch(r'reports/(etl|cdc)/[0-9]+/[a-zA-Z0-9:._-]{1,160}/[0-9-]+_[0-9-]+\.json', key):
        raise HTTPException(404)
    try:
        result = s3.get_object(Bucket=BUCKET, Key=key)
        data = result['Body'].read()
        return Response(data, media_type='application/json',
                        headers={'Cache-Control': 'max-age=3600',
                                 'Content-Disposition': 'attachment; filename="bionicpro-report.json"'})
    except ClientError as error:
        if error.response['Error']['Code'] in ('404', 'NoSuchKey'):
            raise HTTPException(404)
        raise HTTPException(503, 'S3 временно недоступен')
