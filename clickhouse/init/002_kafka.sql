-- Debezium emits envelope JSON; tombstones are skipped by KafkaEngine.
CREATE TABLE IF NOT EXISTS bionicpro.customers_kafka (payload String)
ENGINE = Kafka SETTINGS kafka_broker_list = 'kafka:9092',
 kafka_topic_list = 'crm.public.customers', kafka_group_name = 'clickhouse-customers',
 kafka_format = 'JSONAsString', kafka_skip_broken_messages = 10;
CREATE TABLE IF NOT EXISTS bionicpro.prostheses_kafka (payload String)
ENGINE = Kafka SETTINGS kafka_broker_list = 'kafka:9092',
 kafka_topic_list = 'crm.public.prostheses', kafka_group_name = 'clickhouse-prostheses',
 kafka_format = 'JSONAsString', kafka_skip_broken_messages = 10;
CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.customers_cdc_mv TO bionicpro.crm_customers AS
SELECT if(JSONExtractString(payload, 'op') = 'd',
 JSONExtractUInt(payload, 'before', 'id'), JSONExtractUInt(payload, 'after', 'id')) AS id,
 JSONExtractString(payload, 'after', 'keycloak_subject') AS keycloak_subject,
 JSONExtractString(payload, 'after', 'display_name') AS display_name,
 fromUnixTimestamp64Milli(toInt64(JSONExtractUInt(payload, 'ts_ms'))) AS updated_at,
 toUInt8(JSONExtractString(payload, 'op') = 'd') AS deleted
FROM bionicpro.customers_kafka
WHERE id > 0;
CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.prostheses_cdc_mv TO bionicpro.crm_prostheses AS
SELECT if(JSONExtractString(payload, 'op') = 'd',
 JSONExtractUInt(payload, 'before', 'id'), JSONExtractUInt(payload, 'after', 'id')) AS id,
 JSONExtractUInt(payload, 'after', 'customer_id') AS customer_id,
 JSONExtractString(payload, 'after', 'serial_number') AS serial_number,
 fromUnixTimestamp64Milli(toInt64(JSONExtractUInt(payload, 'ts_ms'))) AS updated_at,
 toUInt8(JSONExtractString(payload, 'op') = 'd') AS deleted
FROM bionicpro.prostheses_kafka
WHERE id > 0;
