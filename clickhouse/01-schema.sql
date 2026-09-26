CREATE DATABASE IF NOT EXISTS bionic;
CREATE TABLE IF NOT EXISTS bionic.clients_etl (
    id UInt64, subject String, display_name String
) ENGINE = MergeTree ORDER BY id;
CREATE TABLE IF NOT EXISTS bionic.clients_cdc (
    id UInt64, subject String, display_name String, version UInt64, deleted UInt8
) ENGINE = ReplacingMergeTree(version) ORDER BY id;
CREATE TABLE IF NOT EXISTS bionic.telemetry (
    id UInt64, client_id UInt64, device_id String, recorded_at DateTime64(3, 'UTC'),
    response_ms Float64, battery UInt8, recognized UInt8, processed_until Date
) ENGINE = MergeTree ORDER BY (client_id, recorded_at, id);
CREATE TABLE IF NOT EXISTS bionic.reports_etl (
    subject String, report_date Date, client_name String, device_count UInt64,
    samples UInt64, avg_response_ms Float64, max_response_ms Float64,
    recognized_pct Float64, min_battery UInt8, generation UInt64, processed_until Date
) ENGINE = MergeTree ORDER BY (subject, report_date);
CREATE TABLE IF NOT EXISTS bionic.reports_cdc AS bionic.reports_etl;
