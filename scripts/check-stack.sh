#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps -a
printf '\nHTTP checks:\n'
for url in http://localhost:3000/ http://localhost:8080/realms/reports-realm/.well-known/openid-configuration http://localhost:8083/connectors http://localhost:8085/health; do
  if curl -fsS -o /dev/null "$url"; then
    printf 'OK   %s\n' "$url"
  else
    printf 'FAIL %s\n' "$url"
  fi
done
printf '\nClickHouse tables:\n'
docker compose exec -T clickhouse sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" -q "SHOW TABLES FROM bionicpro"'
