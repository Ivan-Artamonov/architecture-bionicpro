CREATE TABLE IF NOT EXISTS customers (
  id bigint PRIMARY KEY,
  keycloak_subject text NOT NULL UNIQUE,
  display_name text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS prostheses (
  id bigint PRIMARY KEY,
  customer_id bigint NOT NULL REFERENCES customers(id),
  serial_number text NOT NULL UNIQUE,
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- Populate customers with real Keycloak user UUIDs before running the report DAG.
