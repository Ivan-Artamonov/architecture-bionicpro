from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean

import clickhouse_connect
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook


INPUT_DIR = Path(os.environ.get("AIRFLOW_INPUT_DIR", "/opt/airflow/sample_files"))
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "reports")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "reports")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "reports_password")


def read_csv(name: str) -> list[dict[str, str]]:
    with (INPUT_DIR / name).open(newline="") as source:
        return list(csv.DictReader(source))


def load_fixtures() -> None:
    hook = PostgresHook(postgres_conn_id="write_to_postgres")
    hook.run(
        """
        CREATE TABLE IF NOT EXISTS sample_table (
            id BIGINT PRIMARY KEY,
            order_number BIGINT,
            total NUMERIC(18, 2),
            discount NUMERIC(18, 2),
            buyer_id BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS crm_prostheses (
            buyer_id BIGINT NOT NULL,
            prosthesis_id TEXT PRIMARY KEY,
            product_model TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_identity_map (
            keycloak_sub TEXT PRIMARY KEY,
            buyer_id BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telemetry_events (
            prosthesis_id TEXT NOT NULL,
            event_time TIMESTAMP NOT NULL,
            reaction_time_ms DOUBLE PRECISION NOT NULL,
            battery_level DOUBLE PRECISION NOT NULL,
            signal_quality DOUBLE PRECISION NOT NULL
        );
        TRUNCATE sample_table, crm_prostheses, user_identity_map, telemetry_events;
        """
    )

    hook.insert_rows(
        table="sample_table",
        rows=[
            (
                int(row["id"]),
                int(row["order_number"]),
                float(row["total"]),
                float(row["discount"]),
                int(row["buyer_id"]),
            )
            for row in read_csv("sample.csv")
        ],
        target_fields=["id", "order_number", "total", "discount", "buyer_id"],
    )
    hook.insert_rows(
        table="crm_prostheses",
        rows=[
            (int(row["buyer_id"]), row["prosthesis_id"], row["product_model"])
            for row in read_csv("prostheses.csv")
        ],
        target_fields=["buyer_id", "prosthesis_id", "product_model"],
    )
    hook.insert_rows(
        table="user_identity_map",
        rows=[(row["keycloak_sub"], int(row["buyer_id"])) for row in read_csv("user_identity_map.csv")],
        target_fields=["keycloak_sub", "buyer_id"],
    )
    hook.insert_rows(
        table="telemetry_events",
        rows=[
            (
                row["prosthesis_id"],
                datetime.fromisoformat(row["event_time"]),
                float(row["reaction_time_ms"]),
                float(row["battery_level"]),
                float(row["signal_quality"]),
            )
            for row in read_csv("telemetry.csv")
        ],
        target_fields=[
            "prosthesis_id",
            "event_time",
            "reaction_time_ms",
            "battery_level",
            "signal_quality",
        ],
    )


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[index]


def clickhouse_client():
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DATABASE,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )


def ensure_clickhouse_tables(client) -> None:
    sql = Path("/opt/airflow/dags/sql/create_report_mart.sql").read_text()
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            client.command(statement)


def build_report_mart() -> str:
    hook = PostgresHook(postgres_conn_id="write_to_postgres")
    rows = hook.get_records(
        """
        SELECT
            identity.keycloak_sub,
            telemetry.prosthesis_id,
            prostheses.product_model,
            telemetry.event_time::date AS day,
            telemetry.reaction_time_ms,
            telemetry.battery_level,
            telemetry.signal_quality
        FROM telemetry_events AS telemetry
        JOIN crm_prostheses AS prostheses
          ON prostheses.prosthesis_id = telemetry.prosthesis_id
        JOIN user_identity_map AS identity
          ON identity.buyer_id = prostheses.buyer_id
        ORDER BY identity.keycloak_sub, telemetry.prosthesis_id, day
        """
    )

    grouped = defaultdict(lambda: defaultdict(list))
    for user_id, prosthesis_id, product_model, event_day, reaction, battery, signal in rows:
        key = (user_id, prosthesis_id, product_model, event_day)
        grouped[key]["reaction"].append(float(reaction))
        grouped[key]["battery"].append(float(battery))
        grouped[key]["signal"].append(float(signal))

    client = clickhouse_client()
    ensure_clickhouse_tables(client)
    client.command("TRUNCATE TABLE reports.prosthesis_report_mart")

    report_rows = [
        (
            user_id,
            prosthesis_id,
            event_day,
            product_model,
            len(metrics["reaction"]),
            mean(metrics["reaction"]),
            percentile95(metrics["reaction"]),
            mean(metrics["battery"]),
            mean(metrics["signal"]),
        )
        for (user_id, prosthesis_id, product_model, event_day), metrics in grouped.items()
    ]
    client.insert(
        "reports.prosthesis_report_mart",
        report_rows,
        column_names=[
            "user_id",
            "prosthesis_id",
            "day",
            "product_model",
            "events_count",
            "avg_reaction_time_ms",
            "p95_reaction_time_ms",
            "avg_battery_level",
            "avg_signal_quality",
        ],
    )
    return max(row[2] for row in report_rows).isoformat()


def update_processed_until(**context) -> None:
    processed_until = context["ti"].xcom_pull(task_ids="build_report_mart")
    if not processed_until:
        raise ValueError("The report mart is empty; processed_until cannot be updated")

    client = clickhouse_client()
    ensure_clickhouse_tables(client)
    client.command("TRUNCATE TABLE reports.etl_processing_state")
    client.insert(
        "reports.etl_processing_state",
        [
            (
                "reports_etl",
                date.fromisoformat(processed_until),
                context["run_id"],
                datetime.utcnow(),
            )
        ],
        column_names=["pipeline_name", "processed_until", "run_id", "updated_at"],
    )


with DAG(
    dag_id="reports_etl",
    start_date=datetime(2024, 12, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["bionicpro", "reports"],
) as dag:
    load = PythonOperator(task_id="load_fixtures", python_callable=load_fixtures)
    build = PythonOperator(task_id="build_report_mart", python_callable=build_report_mart)
    state = PythonOperator(task_id="update_processed_until", python_callable=update_processed_until)

    load >> build >> state
