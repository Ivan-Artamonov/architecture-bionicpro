CREATE TABLE IF NOT EXISTS bionic.clients_kafka (raw String)
ENGINE = Kafka SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'crm.public.clients',
    kafka_group_name = 'clickhouse-clients',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 1;

-- Один топик и одна партиция: offset задаёт порядок snapshot, update и delete.
CREATE MATERIALIZED VIEW IF NOT EXISTS bionic.consume_clients TO bionic.clients_cdc AS
SELECT JSONExtractUInt(if(JSONExtractString(raw, 'op') = 'd',
           JSONExtractRaw(raw, 'before'), JSONExtractRaw(raw, 'after')), 'id') AS id,
       JSONExtractString(if(JSONExtractString(raw, 'op') = 'd',
           JSONExtractRaw(raw, 'before'), JSONExtractRaw(raw, 'after')), 'subject') AS subject,
       JSONExtractString(if(JSONExtractString(raw, 'op') = 'd',
           JSONExtractRaw(raw, 'before'), JSONExtractRaw(raw, 'after')), 'display_name') AS display_name,
       toUInt64(_offset + 1) AS version,
       toUInt8(JSONExtractString(raw, 'op') = 'd') AS deleted
FROM bionic.clients_kafka
WHERE JSONExtractString(raw, 'op') IN ('r', 'c', 'u', 'd');
