CREATE TABLE telemetry (
    id bigserial PRIMARY KEY,
    client_id bigint NOT NULL,
    device_id text NOT NULL,
    recorded_at timestamptz NOT NULL,
    response_ms double precision NOT NULL,
    battery integer NOT NULL,
    recognized boolean NOT NULL
);
-- Синтетические данные за два завершённых дня, по два протеза у первого пользователя.
INSERT INTO telemetry(client_id, device_id, recorded_at, response_ms, battery, recognized)
SELECT client_id, 'prosthesis-' || client_id || '-' || (n % 2),
       date_trunc('day', now() AT TIME ZONE 'UTC') - interval '2 days' + n * interval '30 minutes',
       60 + (n % 70), 100 - (n % 80), n % 10 <> 0
FROM generate_series(0, 95) n CROSS JOIN generate_series(1, 2) client_id;
CREATE USER etl_reader WITH PASSWORD 'local-etl';
GRANT SELECT ON telemetry TO etl_reader;
