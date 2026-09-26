WITH (SELECT max(processed_until) FROM bionic.telemetry) AS watermark
-- Версия вычисляется один раз после UNION: у метаданных и строк она одинаковая.
SELECT subject, report_date, client_name, device_count, samples,
       avg_response_ms, max_response_ms, recognized_pct, min_battery,
       toUInt64(toUnixTimestamp64Milli(now64(3))) AS generation,
       watermark AS processed_until
FROM (
    SELECT c.subject AS subject, toDate(t.recorded_at) AS report_date,
           any(c.display_name) AS client_name, uniqExact(t.device_id) AS device_count,
           count() AS samples, round(avg(t.response_ms), 2) AS avg_response_ms,
           max(t.response_ms) AS max_response_ms,
           round(100 * avg(t.recognized), 2) AS recognized_pct, min(t.battery) AS min_battery
    FROM bionic.telemetry t
    INNER JOIN (__CLIENTS__) c ON t.client_id = c.id
    WHERE t.id > 0 AND t.recorded_at < toDateTime(watermark, 'UTC')
    GROUP BY c.subject, toDate(t.recorded_at)
    UNION ALL
    SELECT '', toDate('1970-01-01'), '', toUInt64(0), toUInt64(0),
           toFloat64(0), toFloat64(0), toFloat64(0), toUInt8(0)
)
