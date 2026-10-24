CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SCHEMA crm;
CREATE SCHEMA telemetry;

CREATE TABLE crm.customers (
    customer_id bigint PRIMARY KEY CHECK (customer_id > 0),
    issuer text NOT NULL,
    subject text NOT NULL CHECK (subject <> ''),
    UNIQUE (issuer, subject)
);
CREATE TABLE crm.prosthesis_owners (
    customer_id bigint NOT NULL REFERENCES crm.customers,
    prosthesis_id text NOT NULL,
    model text NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz NOT NULL DEFAULT '2100-01-01T00:00:00Z',
    CHECK (valid_from < valid_to),
    EXCLUDE USING gist (prosthesis_id WITH =, tstzrange(valid_from, valid_to, '[)') WITH &&)
);
CREATE TABLE telemetry.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prosthesis_id text NOT NULL,
    event_time timestamptz NOT NULL,
    response_ms double precision NOT NULL CHECK (response_ms >= 0 AND response_ms < 10000),
    battery_percent smallint NOT NULL CHECK (battery_percent BETWEEN 0 AND 100),
    movement_success boolean NOT NULL
);
CREATE INDEX ON telemetry.events (event_time);

-- Synthetic local fixtures only. Replace subjects with the actual Keycloak user IDs.
INSERT INTO crm.customers VALUES
    (1, 'http://localhost:8080/realms/reports-realm', 'demo-user1'),
    (2, 'http://localhost:8080/realms/reports-realm', 'demo-user2');
INSERT INTO crm.prosthesis_owners VALUES
    (1, 'BP-001', 'Bionic Hand', now() - interval '1 year', '2100-01-01'),
    (1, 'BP-003', 'Bionic Arm', now() - interval '1 year', '2100-01-01'),
    (2, 'BP-002', 'Bionic Hand', now() - interval '1 year', '2100-01-01');
INSERT INTO telemetry.events (prosthesis_id, event_time, response_ms, battery_percent, movement_success)
SELECT device, date_trunc('hour', now()) - n * interval '1 hour',
       CASE WHEN device='BP-002' THEN 120 ELSE 60 END + n % 20,
       100 - n % 70, n % 10 <> 0
FROM unnest(ARRAY['BP-001', 'BP-002', 'BP-003']) AS device CROSS JOIN generate_series(1, 168) AS n;

CREATE USER etl_reader PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE sources TO etl_reader;
GRANT USAGE ON SCHEMA crm, telemetry TO etl_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA crm, telemetry TO etl_reader;
ALTER ROLE etl_reader SET default_transaction_read_only = on;
