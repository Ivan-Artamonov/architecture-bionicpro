import hashlib
import os
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import clickhouse_connect
import psycopg2
from airflow import DAG
from airflow.operators.python import PythonOperator, get_current_context


def warehouse():
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        secure=os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true",
        username="etl", password=os.environ["CLICKHOUSE_ETL_PASSWORD"], database="reports",
        connect_timeout=5, send_receive_timeout=120,
    )


def interval():
    context = get_current_context()
    end = context["data_interval_end"].astimezone(timezone.utc).replace(tzinfo=None)
    # Thirty complete UTC days plus the current partial day, bounded by the DAG interval end.
    start = (end - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    return {"start": start, "end": end, "snapshot": hashlib.sha256(context["run_id"].encode()).hexdigest()}


def copy_source(url, query, table, columns, parameters=None):
    # Server-side cursor and fixed batches: raw telemetry is never put in XCom or loaded all at once.
    with closing(psycopg2.connect(url, connect_timeout=5, options="-c timezone=UTC -c statement_timeout=300000")) as source:
        source.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with source.cursor(name="reports_extract") as cursor, warehouse() as target:
            target.command(f"TRUNCATE TABLE reports.{table}")
            cursor.execute(query, parameters)
            while batch := cursor.fetchmany(10000):
                target.insert(table, batch, column_names=columns)


def extract_crm():
    # Both CRM tables must belong to one consistent snapshot.
    with closing(psycopg2.connect(os.environ["CRM_DATABASE_URL"], connect_timeout=5,
                                 options="-c timezone=UTC -c statement_timeout=300000")) as source, warehouse() as target:
        source.set_session(readonly=True, isolation_level="REPEATABLE READ")
        for table, query, columns in (
            ("clients_stage", "SELECT customer_id, issuer, subject FROM crm.customers",
             ["customer_id", "issuer", "subject"]),
            ("owners_stage", "SELECT customer_id, prosthesis_id, model, valid_from, valid_to FROM crm.prosthesis_owners",
             ["customer_id", "prosthesis_id", "model", "valid_from", "valid_to"]),
        ):
            with source.cursor(name=table) as cursor:
                target.command(f"TRUNCATE TABLE reports.{table}")
                cursor.execute(query)
                while batch := cursor.fetchmany(10000):
                    target.insert(table, batch, column_names=columns)


def extract_telemetry():
    bounds = interval()
    copy_source(os.environ["TELEMETRY_DATABASE_URL"],
                "SELECT event_id, prosthesis_id, event_time, response_ms, battery_percent, movement_success::int "
                "FROM telemetry.events WHERE event_time >= %s AND event_time < %s",
                "telemetry_stage", ["event_id", "prosthesis_id", "event_time", "response_ms",
                                    "battery_percent", "movement_success"],
                (bounds["start"].replace(tzinfo=timezone.utc), bounds["end"].replace(tzinfo=timezone.utc)))


def build_mart():
    with warehouse() as target:
        # Refuse an unexpectedly empty CRM instead of replacing all published reports.
        if target.command("SELECT count() FROM reports.clients_stage") == 0:
            raise ValueError("CRM contains no customers")
        target.command("TRUNCATE TABLE reports.user_reports_next")
        target.command(Path(__file__).with_name("sql").joinpath("build_reports.sql").read_text(), parameters=interval())
        clients = target.command("SELECT count() FROM reports.clients_stage")
        rows, identities = target.query(
            "SELECT count(), uniqExact((issuer, subject)) FROM reports.user_reports_next").first_row
        if rows != clients or identities != clients:
            raise ValueError("Report snapshot has missing or duplicate customer identities")


def publish():
    bounds = interval()
    with warehouse() as target:
        # A retry after a successful EXCHANGE must not swap the old snapshot back into production.
        if target.command("SELECT count() FROM reports.user_reports WHERE snapshot_id={snapshot:String}", parameters=bounds):
            return
        if target.command("SELECT count() FROM reports.user_reports WHERE period_end > {end:DateTime}", parameters=bounds):
            raise ValueError("Cannot replace a newer published snapshot with an older interval")
        if not target.command("SELECT count() FROM reports.user_reports_next WHERE snapshot_id={snapshot:String}", parameters=bounds):
            raise ValueError("Prepared snapshot not found")
        target.command("EXCHANGE TABLES reports.user_reports AND reports.user_reports_next")


with DAG(
    "bionicpro_reports", start_date=datetime(2024, 12, 1, tzinfo=timezone.utc),
    schedule="0 * * * *", catchup=False, max_active_runs=1,
    default_args={"owner": "bionicpro", "retries": 2, "retry_delay": timedelta(minutes=1),
                  "execution_timeout": timedelta(minutes=10)},
    dagrun_timeout=timedelta(minutes=30), tags=["reports"],
) as dag:
    crm = PythonOperator(task_id="extract_crm", python_callable=extract_crm, do_xcom_push=False)
    telemetry = PythonOperator(task_id="extract_telemetry", python_callable=extract_telemetry, do_xcom_push=False)
    mart = PythonOperator(task_id="build_mart", python_callable=build_mart, do_xcom_push=False)
    ready = PythonOperator(task_id="publish", python_callable=publish, do_xcom_push=False)
    [crm, telemetry] >> mart >> ready
