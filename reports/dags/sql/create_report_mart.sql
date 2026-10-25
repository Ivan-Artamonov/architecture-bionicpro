CREATE DATABASE IF NOT EXISTS reports;

CREATE TABLE IF NOT EXISTS reports.prosthesis_report_mart
(
    user_id String,
    prosthesis_id String,
    day Date,
    product_model LowCardinality(String),
    events_count UInt64,
    avg_reaction_time_ms Float64,
    p95_reaction_time_ms Float64,
    avg_battery_level Float64,
    avg_signal_quality Float64
)
ENGINE = MergeTree
ORDER BY (user_id, prosthesis_id, day);

CREATE TABLE IF NOT EXISTS reports.etl_processing_state
(
    pipeline_name String,
    processed_until Date,
    run_id String,
    updated_at DateTime
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY pipeline_name;
