-- Maintenance-only; runner provides transaction, advisory lock and checksum tracking.
-- Save every inbound FK verbatim (including ON DELETE CASCADE), then retarget by name.
CREATE TEMP TABLE day4_order_fks ON COMMIT DROP AS
SELECT conrelid::regclass::text AS relation, conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE contype = 'f' AND confrelid = 'public."order"'::regclass;
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM day4_order_fks LOOP
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.relation, r.conname);
  END LOOP;
END $$;
CREATE TABLE order_day4_new (LIKE "order" INCLUDING ALL) PARTITION BY HASH(order_id);
CREATE TABLE order_h0 PARTITION OF order_day4_new FOR VALUES WITH (MODULUS 4, REMAINDER 0);
CREATE TABLE order_h1 PARTITION OF order_day4_new FOR VALUES WITH (MODULUS 4, REMAINDER 1);
CREATE TABLE order_h2 PARTITION OF order_day4_new FOR VALUES WITH (MODULUS 4, REMAINDER 2);
CREATE TABLE order_h3 PARTITION OF order_day4_new FOR VALUES WITH (MODULUS 4, REMAINDER 3);
INSERT INTO order_day4_new SELECT * FROM "order";
DO $$ BEGIN
  IF EXISTS ((SELECT * FROM "order" EXCEPT ALL SELECT * FROM order_day4_new)
    UNION ALL (SELECT * FROM order_day4_new EXCEPT ALL SELECT * FROM "order")) THEN
    RAISE EXCEPTION 'Order partition reconciliation failed';
  END IF;
END $$;
-- LIKE copies CHECK, NOT NULL, defaults and indexes, but NOT outbound FKs.
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint
      WHERE contype='f' AND conrelid='public."order"'::regclass LOOP
    EXECUTE format('ALTER TABLE order_day4_new ADD CONSTRAINT %I %s', r.conname, r.definition);
  END LOOP;
END $$;
ALTER TABLE "order" RENAME TO order_day4_old;
ALTER TABLE order_day4_new RENAME TO "order";
ALTER SEQUENCE order_order_id_seq OWNED BY "order".order_id;
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT * FROM day4_order_fks LOOP
    EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', r.relation, r.conname, r.definition);
  END LOOP;
END $$;
DROP TABLE order_day4_old;

CREATE TABLE system_log_day4_new (LIKE system_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING STORAGE)
    PARTITION BY RANGE(created_at);
ALTER TABLE system_log_day4_new ADD PRIMARY KEY(log_id, created_at);
DO $$ DECLARE start_month timestamp; end_month timestamp; cursor_month timestamp; BEGIN
  SELECT LEAST(date_trunc('month', min(created_at)), date_trunc('month', CURRENT_TIMESTAMP)::timestamp),
    GREATEST(date_trunc('month', max(created_at)), date_trunc('month', CURRENT_TIMESTAMP)::timestamp)
      + interval '4 months' INTO start_month, end_month FROM system_log;
  IF end_month - start_month > interval '200 years' THEN
    RAISE EXCEPTION 'Log timestamp span exceeds 200 years; review data before partitioning';
  END IF;
  cursor_month := start_month;
  WHILE cursor_month < end_month LOOP
    EXECUTE format('CREATE TABLE %I PARTITION OF system_log_day4_new FOR VALUES FROM (%L) TO (%L)',
      'system_log_' || to_char(cursor_month,'YYYYMM'), cursor_month, cursor_month + interval '1 month');
    cursor_month := cursor_month + interval '1 month';
  END LOOP;
END $$;
CREATE TABLE system_log_default PARTITION OF system_log_day4_new DEFAULT;
INSERT INTO system_log_day4_new SELECT * FROM system_log;
DO $$ BEGIN
  IF EXISTS ((SELECT * FROM system_log EXCEPT ALL SELECT * FROM system_log_day4_new)
    UNION ALL (SELECT * FROM system_log_day4_new EXCEPT ALL SELECT * FROM system_log)) THEN
    RAISE EXCEPTION 'System log partition reconciliation failed';
  END IF;
END $$;
ALTER TABLE system_log RENAME TO system_log_day4_old;
ALTER TABLE system_log_day4_new RENAME TO system_log;
ALTER SEQUENCE system_log_log_id_seq OWNED BY system_log.log_id;
DROP TABLE system_log_day4_old;
ALTER TABLE system_log ADD CONSTRAINT system_log_user_id_fkey FOREIGN KEY(user_id) REFERENCES "user"(user_id);
CREATE INDEX idx_system_log_user ON system_log(user_id);
CREATE INDEX idx_system_log_action ON system_log(action);
CREATE INDEX idx_system_log_created_at ON system_log(created_at);
-- Sequence values are retained, including gaps/reservations; never reset to MAX(id).
