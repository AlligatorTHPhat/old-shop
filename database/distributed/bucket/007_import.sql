CREATE TABLE migration_import(
 source_hash text PRIMARY KEY,state text NOT NULL,started_at timestamptz NOT NULL DEFAULT now()
);
