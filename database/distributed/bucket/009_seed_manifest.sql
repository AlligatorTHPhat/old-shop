CREATE TABLE seed_manifest(
 run_id uuid PRIMARY KEY REFERENCES seed_runs(run_id),
 manifest jsonb NOT NULL, verification jsonb NOT NULL,
 verified_at timestamptz NOT NULL DEFAULT now()
);
