#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/prepare.sh
docker compose up -d --build --wait --wait-timeout 300
docker compose exec -T reports-api python - < scripts/bootstrap.py
docker compose exec -T airflow airflow dags test reports_pipeline
docker compose exec -T airflow airflow dags unpause reports_pipeline
printf '\nОткрыть: https://localhost:8443\n'
