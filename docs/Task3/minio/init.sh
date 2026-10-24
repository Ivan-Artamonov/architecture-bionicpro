#!/bin/sh
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing local/reports
mc anonymous set none local/reports
mc admin user add local reports-api "$REPORTS_S3_SECRET_KEY"
mc admin policy create local reports-api /config/api-policy.json
mc admin policy attach local reports-api --user reports-api
mc admin user add local reports-etl "$ETL_S3_SECRET_KEY"
mc admin policy create local reports-etl /config/etl-policy.json
mc admin policy attach local reports-etl --user reports-etl
mc ilm import local/reports < /config/lifecycle.json
