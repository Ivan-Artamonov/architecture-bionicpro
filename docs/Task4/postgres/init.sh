#!/bin/bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v reader_password="$ETL_DB_PASSWORD" -f /sources.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v cdc_password="$CDC_DB_PASSWORD" -f /cdc.sql
