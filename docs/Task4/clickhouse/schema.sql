CREATE DATABASE IF NOT EXISTS reports ENGINE = Atomic;

CREATE TABLE reports.cdc_state
(
    table_name LowCardinality(String), row_id UInt64, row String,
    version UInt128, deleted UInt8
) ENGINE = ReplacingMergeTree(version) ORDER BY (table_name, row_id);

CREATE TABLE reports.kafka_cdc (message String)
ENGINE = Kafka SETTINGS kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'bionicpro.cdc', kafka_group_name = 'clickhouse-reports-v1',
    kafka_format = 'JSONAsString', kafka_num_consumers = 1,
    kafka_skip_broken_messages = 0;

CREATE MATERIALIZED VIEW reports.ingest_cdc TO reports.cdc_state AS
WITH JSONExtractString(message, 'op') AS op,
     concat(JSONExtractString(message, 'source', 'schema'), '.',
            JSONExtractString(message, 'source', 'table')) AS source_table,
     if(op = 'd', JSONExtractRaw(message, 'before'), JSONExtractRaw(message, 'after')) AS image
SELECT source_table AS table_name,
       JSONExtractUInt(image, multiIf(source_table = 'crm.customers', 'customer_id',
                                      source_table = 'crm.prosthesis_owners', 'ownership_id', 'event_id')) AS row_id,
       image AS row,
       bitShiftLeft(toUInt128(JSONExtractUInt(message, 'source', 'lsn')), 64)
           + toUInt128(_offset) AS version,
       toUInt8(op = 'd') AS deleted
FROM reports.kafka_cdc
WHERE op IN ('r', 'c', 'u', 'd');

-- FINAL выбирает последнюю версию записи, затем исключаются удаления.
CREATE VIEW reports.customers_current AS
SELECT row_id AS customer_id, JSONExtractString(row, 'issuer') AS issuer,
       JSONExtractString(row, 'subject') AS subject
FROM reports.cdc_state FINAL WHERE table_name = 'crm.customers' AND deleted = 0;

CREATE VIEW reports.owners_current AS
SELECT JSONExtractUInt(row, 'customer_id') AS customer_id,
       JSONExtractString(row, 'prosthesis_id') AS prosthesis_id,
       JSONExtractString(row, 'model') AS model,
       parseDateTime64BestEffort(JSONExtractString(row, 'valid_from'), 3, 'UTC') AS valid_from,
       parseDateTime64BestEffort(JSONExtractString(row, 'valid_to'), 3, 'UTC') AS valid_to
FROM reports.cdc_state FINAL WHERE table_name = 'crm.prosthesis_owners' AND deleted = 0;

CREATE VIEW reports.telemetry_current AS
SELECT row_id AS event_id, JSONExtractString(row, 'prosthesis_id') AS prosthesis_id,
       parseDateTime64BestEffort(JSONExtractString(row, 'event_time'), 3, 'UTC') AS event_time,
       JSONExtractFloat(row, 'response_ms') AS response_ms,
       toUInt8(JSONExtractUInt(row, 'battery_percent')) AS battery_percent,
       toUInt8(JSONExtractBool(row, 'movement_success')) AS movement_success
FROM reports.cdc_state FINAL WHERE table_name = 'telemetry.events' AND deleted = 0;

CREATE TABLE reports.user_reports_cdc
(
    issuer String, subject String, customer_id UInt64,
    period_start Date, period_end DateTime('UTC'), prepared_at DateTime('UTC'), snapshot_id String,
    daily Array(Tuple(day Date, prosthesis_id String, model String, samples UInt64,
                      avg_response_ms Float64, max_response_ms Float64,
                      min_battery_percent UInt8, successful_movements UInt64))
) ENGINE = MergeTree ORDER BY (issuer, subject, customer_id);

-- Пересчёт выполняется в ClickHouse. В версии 24.8 требуется этот флаг.
SET allow_experimental_refreshable_materialized_view = 1;
CREATE MATERIALIZED VIEW reports.refresh_user_reports
REFRESH EVERY 1 MINUTE TO reports.user_reports_cdc AS
WITH now('UTC') AS report_end,
     toStartOfDay(report_end - INTERVAL 30 DAY) AS report_start,
daily_metrics AS (
    SELECT o.customer_id, toDate(t.event_time, 'UTC') AS day, t.prosthesis_id,
           any(o.model) AS model, count() AS samples,
           round(avg(t.response_ms), 2) AS avg_response_ms,
           max(t.response_ms) AS max_response_ms,
           min(t.battery_percent) AS min_battery_percent,
           countIf(t.movement_success = 1) AS successful_movements
    FROM reports.telemetry_current t
    INNER JOIN reports.owners_current o ON t.prosthesis_id = o.prosthesis_id
    WHERE t.event_time >= report_start AND t.event_time < report_end
      AND t.event_time >= o.valid_from AND t.event_time < o.valid_to
    GROUP BY o.customer_id, day, t.prosthesis_id
),
customer_reports AS (
    SELECT customer_id,
           arraySort(x -> (x.1, x.2), groupArray((day, prosthesis_id, model, samples,
                     avg_response_ms, max_response_ms, min_battery_percent, successful_movements))) AS daily
    FROM daily_metrics
    GROUP BY customer_id
)
SELECT c.issuer, c.subject, c.customer_id, toDate(report_start) AS period_start,
       report_end AS period_end, report_end AS prepared_at,
       lower(hex(SHA256(toString(report_end)))) AS snapshot_id, d.daily AS daily
FROM reports.customers_current c
LEFT JOIN customer_reports d ON c.customer_id = d.customer_id;
