-- Additive bucket-v2 objects. Run only through scripts.bucket_schema.
CREATE TABLE bucket_installation (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 instance_id uuid NOT NULL DEFAULT gen_random_uuid(),
 kind text NOT NULL CHECK(kind IN ('core','site')), site_id text,
 dataset_id text NOT NULL, contract_digest text NOT NULL, schema_digest text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE app_event (
 event_id bigserial PRIMARY KEY, entity text NOT NULL, entity_id integer NOT NULL,
 operation text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE app_delivery (
 event_id bigint NOT NULL REFERENCES app_event(event_id), target text NOT NULL CHECK(target IN ('mongo','graph')),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','dead')),
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 error_code text, PRIMARY KEY(event_id,target)
);
CREATE INDEX app_delivery_pending ON app_delivery(target,available_at,event_id) WHERE status='pending';
CREATE FUNCTION bucket_emit(entity text, id integer, operation text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE eid bigint;
BEGIN
 INSERT INTO app_event(entity,entity_id,operation) VALUES(entity,id,operation) RETURNING event_id INTO eid;
 INSERT INTO app_delivery(event_id,target) VALUES(eid,'mongo'),(eid,'graph');
END $$;
