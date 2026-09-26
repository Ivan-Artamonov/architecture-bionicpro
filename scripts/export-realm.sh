#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose stop keycloak
trap 'docker compose up -d keycloak' EXIT
mkdir -p keycloak/runtime-export
docker compose run --rm --no-deps --user 0:0 -v "$(pwd)/keycloak/runtime-export:/export" \
  keycloak export --realm reports-realm --file /export/realm.json
chmod 600 keycloak/runtime-export/realm.json
printf '\nЭкспорт: keycloak/runtime-export/realm.json (содержит секреты и OTP, не для публикации).\n'
