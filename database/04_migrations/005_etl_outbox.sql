-- D7 confirmed 2026-10-30: all pre-migration naive timestamps are Vietnamese local time.
-- Source timestamps remain untouched. Future backend transactions use UTC; SQL uses session timezone.
CREATE TABLE etl_time_origin (
 source_table text NOT NULL, source_key jsonb NOT NULL, field_name text NOT NULL,
 source_value timestamp NOT NULL, source_zone text NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(source_table,source_key,field_name)
);
CREATE TABLE etl_outbox (
 event_id bigserial PRIMARY KEY, source_table text NOT NULL, source_key jsonb NOT NULL,
 entity_type text NOT NULL CHECK(entity_type IN ('product','order','review','system_log','violation_log','contact')),
 entity_key jsonb NOT NULL, operation text NOT NULL CHECK(operation IN ('INSERT','UPDATE','DELETE')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','dead')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0), processed_at timestamptz,
 last_error_code varchar(80), last_run_id uuid
);
CREATE INDEX idx_etl_outbox_pending ON etl_outbox(available_at,event_id) WHERE status IN ('pending','dead');
CREATE TABLE etl_runs (
 run_id uuid PRIMARY KEY, mode text NOT NULL, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 ended_at timestamptz, status text NOT NULL DEFAULT 'running', rows_in bigint NOT NULL DEFAULT 0,
 rows_out bigint NOT NULL DEFAULT 0, errors integer NOT NULL DEFAULT 0, details jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE etl_state(name text PRIMARY KEY,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE report_daily_sales (
 report_date date NOT NULL,seller_id integer NOT NULL,category_id integer NOT NULL,
 orders_count bigint NOT NULL,item_quantity bigint NOT NULL,gross_sales_vnd numeric(30,0) NOT NULL,
 refreshed_at timestamptz NOT NULL,run_id uuid NOT NULL,
 PRIMARY KEY(report_date,seller_id,category_id)
);
-- Explicit classification of existing data; never infer timestamp origin from serial IDs.
DO $$ DECLARE spec record; field text; key_expr text; BEGIN
 FOR spec IN SELECT * FROM (VALUES
  ('product','product_id',ARRAY['created_at','updated_at']),
  ('order','order_id',ARRAY['order_date']),('review','review_id',ARRAY['created_at','updated_at']),
  ('system_log','log_id',ARRAY['created_at']),('violation_log','log_id',ARRAY['created_at']),
  ('system_feedback','feedback_id',ARRAY['created_at'])
 ) AS v(table_name,id_column,fields) LOOP
  key_expr := format('jsonb_build_object(%L,%I)',spec.id_column,spec.id_column);
  IF spec.table_name='system_log' THEN key_expr := format('jsonb_build_object(''log_id'',log_id,''created_at'',created_at)'); END IF;
  FOREACH field IN ARRAY spec.fields LOOP
   EXECUTE format('INSERT INTO etl_time_origin(source_table,source_key,field_name,source_value,source_zone)
    SELECT %L,%s,%L,%I,''Asia/Ho_Chi_Minh'' FROM %I WHERE %I IS NOT NULL',
    spec.table_name,key_expr,field,field,spec.table_name,field);
  END LOOP;
 END LOOP;
END $$;
CREATE FUNCTION etl_capture_change() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
DECLARE
 table_name text := TG_ARGV[0]; id_column text := TG_ARGV[1];
 before_row jsonb; after_row jsonb; source_key jsonb; old_key jsonb; new_key jsonb;
 fields text[] := '{}'; field text; zone text; targets jsonb := '[]';
 candidate jsonb; target jsonb; related record; source_id bigint;
BEGIN
 IF TG_OP<>'INSERT' THEN before_row:=to_jsonb(OLD); END IF;
 IF TG_OP<>'DELETE' THEN after_row:=to_jsonb(NEW); END IF;
 old_key:=jsonb_build_object(id_column,before_row->id_column);
 new_key:=jsonb_build_object(id_column,after_row->id_column);
 IF table_name='system_log' THEN
  old_key:=old_key||jsonb_build_object('created_at',before_row->'created_at');
  new_key:=new_key||jsonb_build_object('created_at',after_row->'created_at');
 END IF;
 fields:=CASE table_name WHEN 'product' THEN ARRAY['created_at','updated_at']
  WHEN 'order' THEN ARRAY['order_date'] WHEN 'review' THEN ARRAY['created_at','updated_at']
  WHEN 'system_log' THEN ARRAY['created_at'] WHEN 'violation_log' THEN ARRAY['created_at']
  WHEN 'system_feedback' THEN ARRAY['created_at'] ELSE '{}'::text[] END;
 IF TG_OP<>'DELETE' THEN
  FOREACH field IN ARRAY fields LOOP
   IF after_row->>field IS NULL THEN CONTINUE; END IF;
   zone:=NULL;
   IF TG_OP='UPDATE' AND after_row->>field IS NOT DISTINCT FROM before_row->>field THEN
    SELECT source_zone INTO zone FROM etl_time_origin
     WHERE source_table=table_name AND etl_time_origin.source_key=old_key AND field_name=field
      AND source_value=(before_row->>field)::timestamp;
   END IF;
   -- An unchanged legacy value without provenance is deliberately not guessed.
   IF zone IS NULL AND TG_OP='UPDATE' AND after_row->>field IS NOT DISTINCT FROM before_row->>field THEN
    CONTINUE;
   END IF;
   INSERT INTO etl_time_origin(source_table,source_key,field_name,source_value,source_zone)
    VALUES(table_name,new_key,field,(after_row->>field)::timestamp,COALESCE(zone,current_setting('TimeZone')))
    ON CONFLICT ON CONSTRAINT etl_time_origin_pkey DO UPDATE SET
     source_value=excluded.source_value,source_zone=excluded.source_zone,recorded_at=clock_timestamp();
  END LOOP;
 END IF;
 FOR candidate IN SELECT value FROM jsonb_array_elements(jsonb_build_array(before_row,after_row))
  WHERE value<>'null'::jsonb LOOP
  source_id:=(candidate->>id_column)::bigint;
  IF table_name IN ('product','order','review','violation_log','system_feedback','system_log') THEN
   target:=jsonb_build_object('id',source_id);
   IF table_name='system_log' THEN target:=target||jsonb_build_object('created_at',candidate->'created_at'); END IF;
   targets:=targets||jsonb_build_array(jsonb_build_object('entity',CASE table_name
    WHEN 'system_feedback' THEN 'contact' ELSE table_name END,'key',target));
  ELSIF table_name='product_image' THEN
   targets:=targets||jsonb_build_array(jsonb_build_object('entity','product','key',jsonb_build_object('id',candidate->'product_id')));
  ELSIF table_name IN ('order_detail','transaction') THEN
   targets:=targets||jsonb_build_array(jsonb_build_object('entity','order','key',jsonb_build_object('id',candidate->'order_id')));
  END IF;
  -- Rebuild snapshots whose CURRENT dimensions/voucher metadata changed, not historical prices.
  IF table_name='product' THEN
   FOR related IN SELECT DISTINCT order_id FROM order_detail WHERE product_id=source_id LOOP
    targets:=targets||jsonb_build_array(jsonb_build_object('entity','order','key',jsonb_build_object('id',related.order_id)));
   END LOOP;
  ELSIF table_name='voucher' THEN
   FOR related IN SELECT order_id FROM "order" WHERE voucher_id=source_id LOOP
    targets:=targets||jsonb_build_array(jsonb_build_object('entity','order','key',jsonb_build_object('id',related.order_id)));
   END LOOP;
  END IF;
 END LOOP;
 source_key:=CASE WHEN TG_OP='DELETE' THEN old_key ELSE new_key END;
 FOR target IN SELECT DISTINCT value FROM jsonb_array_elements(targets) LOOP
  INSERT INTO etl_outbox(source_table,source_key,entity_type,entity_key,operation)
   VALUES(table_name,source_key,target->>'entity',target->'key',TG_OP);
 END LOOP;
 RETURN COALESCE(NEW,OLD);
END $$;
DO $$ DECLARE spec record; BEGIN
 FOR spec IN SELECT * FROM (VALUES
  ('product','product_id'),('product_image','image_id'),('order','order_id'),
  ('order_detail','order_detail_id'),('transaction','transaction_id'),('voucher','voucher_id'),
  ('review','review_id'),('system_log','log_id'),('violation_log','log_id'),('system_feedback','feedback_id')
 ) AS v(table_name,id_column) LOOP
  EXECUTE format('CREATE TRIGGER trg_etl_capture AFTER INSERT OR UPDATE OR DELETE ON %I
   FOR EACH ROW EXECUTE FUNCTION etl_capture_change(%L,%L)',spec.table_name,spec.table_name,spec.id_column);
 END LOOP;
END $$;
