-- Stable identity is needed to update/delete an ownership interval in ClickHouse.
ALTER TABLE crm.prosthesis_owners ADD COLUMN ownership_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY;
ALTER TABLE crm.customers REPLICA IDENTITY FULL;
ALTER TABLE crm.prosthesis_owners REPLICA IDENTITY FULL;
ALTER TABLE telemetry.events REPLICA IDENTITY FULL;

CREATE ROLE debezium LOGIN REPLICATION PASSWORD :'cdc_password';
GRANT CONNECT ON DATABASE sources TO debezium;
GRANT USAGE ON SCHEMA crm, telemetry TO debezium;
GRANT SELECT ON crm.customers, crm.prosthesis_owners, telemetry.events TO debezium;
CREATE PUBLICATION bionicpro_cdc FOR TABLE crm.customers, crm.prosthesis_owners, telemetry.events;
-- No recurring full exports by the old ETL role in this stand.
ALTER ROLE etl_reader NOLOGIN;
