import json
import os
from datetime import timedelta
from pathlib import Path

import httpx
import pendulum
import psycopg
from airflow.decorators import dag, task


def clickhouse(sql):
    response = httpx.post('http://clickhouse:8123', content=sql.encode(), timeout=60,
                          auth=('bionic', os.getenv('CLICKHOUSE_PASSWORD', 'local-clickhouse')))
    response.raise_for_status()


def insert(table, rows):
    if rows:
        clickhouse(f'INSERT INTO bionic.{table} FORMAT JSONEachRow\n' +
                   '\n'.join(json.dumps(r, default=str) for r in rows))


@dag(schedule='0 * * * *', start_date=pendulum.datetime(2026, 1, 1, tz='UTC'),
     catchup=False, max_active_runs=1, tags=['bionicpro'],
     default_args={'retries': 2, 'retry_delay': timedelta(seconds=30)})
def reports_pipeline():
    @task
    def load_sources_and_publish(data_interval_end=None):
        # Полный снимок подхватывает исправления без дублей при повторном запуске.
        cutoff = data_interval_end.in_timezone('UTC').date()
        clickhouse('DROP TABLE IF EXISTS bionic.telemetry_stage')
        clickhouse('CREATE TABLE bionic.telemetry_stage AS bionic.telemetry')
        with psycopg.connect(os.environ['TELEMETRY_DSN']) as db:
            rows = db.execute('''SELECT id, client_id, device_id,
                to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.MS'),
                response_ms, battery, recognized FROM telemetry
                WHERE recorded_at < %s::date AT TIME ZONE 'UTC' ORDER BY id''', (cutoff,)).fetchall()
        data = [dict(zip(('id', 'client_id', 'device_id', 'recorded_at', 'response_ms',
                          'battery', 'recognized'), (*r[:6], int(r[6])))) for r in rows]
        for row in data:
            row['processed_until'] = str(cutoff)
        # Служебная строка сохраняет watermark даже при пустом источнике.
        data.append({'id': 0, 'client_id': 0, 'device_id': '', 'recorded_at': '1970-01-01 00:00:00',
                     'response_ms': 0, 'battery': 0, 'recognized': 0, 'processed_until': str(cutoff)})
        insert('telemetry_stage', data)
        clickhouse('EXCHANGE TABLES bionic.telemetry AND bionic.telemetry_stage')
        if os.getenv('REPORT_SOURCE', 'cdc') == 'etl':
            with psycopg.connect(os.environ['CRM_DSN']) as db:
                clients = db.execute('SELECT id, subject, display_name FROM clients').fetchall()
            clickhouse('TRUNCATE TABLE bionic.clients_etl')
            insert('clients_etl', [dict(zip(('id', 'subject', 'display_name'), r)) for r in clients])
            clickhouse('DROP TABLE IF EXISTS bionic.reports_etl_stage')
            clickhouse('CREATE TABLE bionic.reports_etl_stage AS bionic.reports_etl')
            sql = Path('/opt/airflow/sql/report-select.sql').read_text().replace(
                '__CLIENTS__', 'SELECT * FROM bionic.clients_etl')
            clickhouse('INSERT INTO bionic.reports_etl_stage ' + sql)
            clickhouse('EXCHANGE TABLES bionic.reports_etl AND bionic.reports_etl_stage')
        else:
            clickhouse('SYSTEM REFRESH VIEW bionic.refresh_reports_cdc')
            clickhouse('SYSTEM WAIT VIEW bionic.refresh_reports_cdc')
    load_sources_and_publish()


reports_pipeline()
