#!/bin/bash
set -euo pipefail
for topic in connect-configs connect-offsets connect-status; do
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists \
    --topic "$topic" --partitions 1 --replication-factor 1 --config cleanup.policy=compact
done
# One partition preserves the order across tables; never compact colliding table keys.
/opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --create --if-not-exists \
  --topic bionicpro.cdc --partitions 1 --replication-factor 1 \
  --config cleanup.policy=delete --config retention.ms=604800000
