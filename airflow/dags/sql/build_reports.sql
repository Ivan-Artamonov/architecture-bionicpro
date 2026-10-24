INSERT INTO reports.user_reports_next
SELECT c.issuer, c.subject, c.customer_id, toDate({start:DateTime}),
       {end:DateTime}, now('UTC'), {snapshot:String}, d.daily
FROM reports.clients_stage c
LEFT JOIN (
    SELECT customer_id,
           arraySort(x -> (x.1, x.2), groupArray((day, prosthesis_id, model, samples,
                     avg_response_ms, max_response_ms, min_battery_percent, successful_movements))) AS daily
    FROM (
        SELECT o.customer_id, toDate(t.event_time, 'UTC') AS day, t.prosthesis_id,
               any(o.model) AS model, count() AS samples,
               round(avg(t.response_ms), 2) AS avg_response_ms,
               max(t.response_ms) AS max_response_ms,
               min(t.battery_percent) AS min_battery_percent,
               countIf(t.movement_success = 1) AS successful_movements
        FROM reports.telemetry_stage t
        INNER JOIN reports.owners_stage o ON t.prosthesis_id = o.prosthesis_id
        WHERE t.event_time >= o.valid_from AND t.event_time < o.valid_to
        GROUP BY o.customer_id, day, t.prosthesis_id
    )
    GROUP BY customer_id
) d ON c.customer_id = d.customer_id
