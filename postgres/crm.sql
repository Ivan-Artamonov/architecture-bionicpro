CREATE TABLE clients (
    id bigint PRIMARY KEY,
    subject text NOT NULL UNIQUE,
    display_name text NOT NULL
);
INSERT INTO clients VALUES
(1, '11111111-1111-4111-8111-111111111111', 'Первый пользователь'),
(2, '22222222-2222-4222-8222-222222222222', 'Второй пользователь');
CREATE TABLE profiles (
    subject text PRIMARY KEY,
    consent boolean NOT NULL,
    profile jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE clients REPLICA IDENTITY FULL;
CREATE USER debezium WITH REPLICATION PASSWORD 'local-debezium';
GRANT CONNECT ON DATABASE crm TO debezium;
GRANT USAGE ON SCHEMA public TO debezium;
GRANT SELECT ON clients TO debezium;
CREATE PUBLICATION bionic_clients FOR TABLE clients;
CREATE USER etl_reader WITH PASSWORD 'local-etl';
GRANT SELECT ON clients TO etl_reader;
CREATE USER profile_app WITH PASSWORD 'local-profile';
GRANT SELECT, INSERT, UPDATE ON profiles TO profile_app;
