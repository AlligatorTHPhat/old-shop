CREATE TABLE bucket_lease(bucket_id integer PRIMARY KEY CHECK(bucket_id BETWEEN 0 AND 255),
 ownership_epoch bigint NOT NULL,state text NOT NULL CHECK(state IN ('active','frozen','staging')));
CREATE TABLE seller_bucket(seller_id integer PRIMARY KEY REFERENCES user_core(user_id),bucket_id integer NOT NULL REFERENCES bucket_lease(bucket_id));
ALTER TABLE product ADD COLUMN bucket_id integer NOT NULL REFERENCES bucket_lease(bucket_id),
 ADD COLUMN catalogue_revision bigint NOT NULL DEFAULT 1;
CREATE TABLE stock_reservation(
 reservation_id uuid PRIMARY KEY,operation_id uuid NOT NULL UNIQUE,product_id integer NOT NULL REFERENCES product(product_id),
 buyer_id integer NOT NULL,quantity integer NOT NULL CHECK(quantity>0),price numeric(18,2) NOT NULL,
 state text NOT NULL CHECK(state IN ('held','committed','released')),expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION enforce_bucket_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE bid integer; lease bucket_lease%ROWTYPE; expected bigint;
BEGIN
 IF current_setting('oldshop.maintenance',true)='on' AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND rolsuper) THEN
   RETURN COALESCE(NEW,OLD);
 END IF;
 bid:=CASE WHEN TG_OP='DELETE' THEN OLD.bucket_id ELSE NEW.bucket_id END;
 SELECT * INTO STRICT lease FROM bucket_lease WHERE bucket_id=bid FOR SHARE;
 expected:=NULLIF(current_setting('oldshop.ownership_epoch',true),'')::bigint;
 IF lease.state<>'active' OR expected IS DISTINCT FROM lease.ownership_epoch THEN
   RAISE EXCEPTION 'bucket_fenced' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND (NEW.product_id,NEW.seller_id,NEW.bucket_id) IS DISTINCT FROM (OLD.product_id,OLD.seller_id,OLD.bucket_id) THEN
   RAISE EXCEPTION 'product_ownership_immutable' USING ERRCODE='23514';
 END IF;
 IF TG_OP<>'DELETE' AND NOT EXISTS(SELECT 1 FROM seller_bucket WHERE seller_id=NEW.seller_id AND bucket_id=NEW.bucket_id) THEN
   RAISE EXCEPTION 'seller_bucket_mismatch' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' THEN NEW.catalogue_revision:=OLD.catalogue_revision+1; END IF;
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE TRIGGER product_bucket BEFORE INSERT OR UPDATE OR DELETE ON product FOR EACH ROW EXECUTE FUNCTION enforce_bucket_owner();
CREATE FUNCTION image_bucket_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE pid integer;
BEGIN
 pid:=CASE WHEN TG_OP='DELETE' THEN OLD.product_id ELSE NEW.product_id END;
 IF TG_OP='UPDATE' AND (NEW.image_id,NEW.product_id) IS DISTINCT FROM (OLD.image_id,OLD.product_id) THEN
   RAISE EXCEPTION 'image_ownership_immutable';
 END IF;
 UPDATE product SET updated_at=clock_timestamp() AT TIME ZONE 'UTC' WHERE product_id=pid;
 IF NOT FOUND THEN RAISE EXCEPTION 'image_parent_missing'; END IF;
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE TRIGGER image_bucket BEFORE INSERT OR UPDATE OR DELETE ON product_image FOR EACH ROW EXECUTE FUNCTION image_bucket_event();
CREATE FUNCTION product_bucket_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF current_setting('oldshop.maintenance',true) IS DISTINCT FROM 'on' THEN
   PERFORM bucket_emit('product',COALESCE(NEW.product_id,OLD.product_id),TG_OP);
 END IF;
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE TRIGGER product_graph AFTER INSERT OR UPDATE OR DELETE ON product FOR EACH ROW EXECUTE FUNCTION product_bucket_event();
