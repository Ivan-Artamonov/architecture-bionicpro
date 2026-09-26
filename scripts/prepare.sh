#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then cp .env.example .env; fi
mkdir -p certs
if [ ! -f certs/localhost.key ]; then
  cat > certs/openssl.cnf <<'CONF'
[req]
distinguished_name = dn
x509_extensions = extensions
prompt = no
[dn]
CN = localhost
[extensions]
subjectAltName = DNS:localhost,IP:127.0.0.1
CONF
  openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
    -keyout certs/localhost.key -out certs/localhost.crt -config certs/openssl.cnf
  chmod 600 certs/localhost.key
fi
