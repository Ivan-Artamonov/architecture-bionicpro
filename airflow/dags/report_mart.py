"""Daily report materialization after CRM CDC and telemetry ingestion."""
from datetime import datetime, timedelta, timezone
import os
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

CH = os.getenv('CLICKHOUSE_URL', 'http://clickhouse:8123/?database=bionicpro')


def execute(sql):
    response = requests.post(CH, data=sql.encode(), timeout=120)
    response.raise_for_status()
    return response.text


def build_mart(**context):
    day = (context['data_interval_end'] - timedelta(days=1)).date().isoformat()
    execute(f"""
        INSERT INTO report_mart
        SELECT c.keycloak_subject, p.id, toDate('{day}'),
               sum(t.signal_count), sum(t.movement_count), now64(3)
        FROM telemetry_daily AS t
        INNER JOIN crm_prostheses AS p FINAL ON p.id = t.prosthesis_id AND p.deleted = 0
        INNER JOIN crm_customers AS c FINAL ON c.id = p.customer_id AND c.deleted = 0
        WHERE t.period_end = toDate('{day}') AND c.keycloak_subject != ''
        GROUP BY c.keycloak_subject, p.id
    """)
    execute(f"INSERT INTO etl_watermark VALUES (toDate('{day}'), now64(3))")


with DAG('bionicpro_daily_reports', start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
         schedule='0 2 * * *', catchup=False, max_active_runs=1,
         default_args={'retries': 3, 'retry_delay': timedelta(minutes=5)}) as dag:
    PythonOperator(task_id='build_report_mart', python_callable=build_mart)
