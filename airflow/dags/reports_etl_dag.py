"""ETL: CRM + telemetry → OLAP report_mart. Schedule: daily 02:00."""
import os
from datetime import datetime, timedelta

import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "bionicpro",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

BUILD_MART_SQL = """
INSERT INTO report_mart (
    user_id, full_name, email, prosthesis_model,
    total_steps, total_distance_m, avg_load_kg,
    sessions_count, last_activity_at, updated_at
)
SELECT
    c.user_id,
    c.full_name,
    c.email,
    c.prosthesis_model,
    COALESCE(SUM(t.steps), 0),
    COALESCE(SUM(t.distance_m), 0),
    COALESCE(AVG(t.load_kg), 0),
    COUNT(t.id),
    MAX(t.recorded_at),
    NOW()
FROM crm_clients c
LEFT JOIN telemetry t ON t.user_id = c.user_id
GROUP BY c.user_id, c.full_name, c.email, c.prosthesis_model
ON CONFLICT (user_id) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email,
    prosthesis_model = EXCLUDED.prosthesis_model,
    total_steps = EXCLUDED.total_steps,
    total_distance_m = EXCLUDED.total_distance_m,
    avg_load_kg = EXCLUDED.avg_load_kg,
    sessions_count = EXCLUDED.sessions_count,
    last_activity_at = EXCLUDED.last_activity_at,
    updated_at = NOW();
"""


def build_report_mart(**_):
    conn = psycopg2.connect(os.environ["OLAP_DSN"])
    try:
        with conn.cursor() as cur:
            cur.execute(BUILD_MART_SQL)
        conn.commit()
    finally:
        conn.close()


with DAG(
    dag_id="reports_etl",
    default_args=default_args,
    description="CRM + telemetry → report_mart",
    schedule_interval="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["reports", "etl"],
) as dag:
    PythonOperator(
        task_id="build_report_mart",
        python_callable=build_report_mart,
    )
