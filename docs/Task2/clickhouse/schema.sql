CREATE DATABASE IF NOT EXISTS reports ENGINE = Atomic;

CREATE TABLE IF NOT EXISTS reports.clients_stage
(
    customer_id UInt64, issuer String, subject String
) ENGINE = MergeTree ORDER BY customer_id;

CREATE TABLE IF NOT EXISTS reports.owners_stage
(
    customer_id UInt64, prosthesis_id String, model String,
    valid_from DateTime64(3, 'UTC'), valid_to DateTime64(3, 'UTC')
) ENGINE = MergeTree ORDER BY (prosthesis_id, valid_from);

CREATE TABLE IF NOT EXISTS reports.telemetry_stage
(
    event_id UInt64, prosthesis_id String, event_time DateTime64(3, 'UTC'),
    response_ms Float64, battery_percent UInt8, movement_success UInt8
) ENGINE = MergeTree ORDER BY (prosthesis_id, event_time, event_id);

CREATE TABLE IF NOT EXISTS reports.user_reports
(
    issuer String, subject String, customer_id UInt64,
    period_start Date, period_end DateTime('UTC'), prepared_at DateTime('UTC'), snapshot_id String,
    daily Array(Tuple(day Date, prosthesis_id String, model String, samples UInt64,
                      avg_response_ms Float64, max_response_ms Float64,
                      min_battery_percent UInt8, successful_movements UInt64))
) ENGINE = MergeTree ORDER BY (issuer, subject, customer_id);

CREATE TABLE IF NOT EXISTS reports.user_reports_next AS reports.user_reports;
