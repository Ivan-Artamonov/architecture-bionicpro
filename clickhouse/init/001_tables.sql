CREATE DATABASE IF NOT EXISTS bionicpro;
CREATE TABLE IF NOT EXISTS bionicpro.telemetry
(
  prosthesis_id UInt64,
  event_time DateTime64(3, 'UTC'),
  movement UInt8,
  signal_strength Float64
) ENGINE = MergeTree ORDER BY (prosthesis_id, event_time);
CREATE TABLE IF NOT EXISTS bionicpro.crm_customers
(
  id UInt64, keycloak_subject String, display_name String,
  updated_at DateTime64(3, 'UTC'), deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY id;
CREATE TABLE IF NOT EXISTS bionicpro.crm_prostheses
(
  id UInt64, customer_id UInt64, serial_number String,
  updated_at DateTime64(3, 'UTC'), deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY id;
CREATE TABLE IF NOT EXISTS bionicpro.report_mart
(
  customer_subject String, prosthesis_id UInt64, period_end Date,
  signal_count UInt64, movement_count UInt64, generated_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (customer_subject, prosthesis_id, period_end);
CREATE TABLE IF NOT EXISTS bionicpro.etl_watermark
(processed_through Date, completed_at DateTime64(3, 'UTC'))
ENGINE = ReplacingMergeTree(completed_at) ORDER BY processed_through;
CREATE TABLE IF NOT EXISTS bionicpro.telemetry_daily
(prosthesis_id UInt64, period_end Date, signal_count UInt64, movement_count UInt64)
ENGINE = SummingMergeTree ORDER BY (prosthesis_id, period_end);
CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.telemetry_daily_mv
TO bionicpro.telemetry_daily AS
SELECT prosthesis_id, toDate(event_time) AS period_end,
 count() AS signal_count, sum(toUInt64(movement)) AS movement_count
FROM bionicpro.telemetry GROUP BY prosthesis_id, period_end;
