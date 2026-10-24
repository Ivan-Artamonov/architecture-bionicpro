#!/bin/bash
set -euo pipefail
clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery < /schema.sql
clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --param_reader_password="$CLICKHOUSE_READER_PASSWORD" \
  --query 'CREATE USER IF NOT EXISTS reports_reader IDENTIFIED WITH sha256_password BY {reader_password:String}'
clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
  --query 'GRANT SELECT ON reports.user_reports_cdc TO reports_reader'
