import json
import time
from pathlib import Path

import boto3
import httpx
from botocore.exceptions import ClientError, EndpointConnectionError


def wait(action):
    for attempt in range(90):
        try:
            return action()
        except (httpx.HTTPError, ClientError, EndpointConnectionError):
            if attempt == 89:
                raise
            time.sleep(2)


def sql(text):
    response = httpx.post('http://clickhouse:8123', content=text.encode(),
                          auth=('bionic', 'local-clickhouse'), timeout=30)
    response.raise_for_status()


s3 = boto3.client('s3', endpoint_url='http://minio:9000',
                  aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin-local',
                  region_name='us-east-1')
wait(s3.list_buckets)
if not any(b['Name'] == 'reports' for b in s3.list_buckets()['Buckets']):
    s3.create_bucket(Bucket='reports')
s3.put_bucket_lifecycle_configuration(Bucket='reports', LifecycleConfiguration={
    'Rules': [{'ID': 'old-reports', 'Status': 'Enabled', 'Filter': {'Prefix': 'reports/'},
               'Expiration': {'Days': 7}}]})

connector = json.loads(Path('/config/debezium/connector.json').read_text())
def configure_connector():
    response = httpx.put('http://kafka-connect:8083/connectors/crm-clients/config',
                         json=connector['config'], timeout=20)
    response.raise_for_status()
wait(configure_connector)
for filename in ('02-cdc.sql', '03-mart.sql'):
    for statement in Path('/config/clickhouse', filename).read_text().split(';'):
        if statement.strip():
            sql(statement)
print('MinIO, Debezium, KafkaEngine и витрина CDC настроены.')
