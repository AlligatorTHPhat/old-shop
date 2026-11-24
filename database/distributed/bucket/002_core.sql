CREATE TABLE site_registry(site_id text PRIMARY KEY, dsn_alias text NOT NULL UNIQUE, active boolean NOT NULL DEFAULT true);
CREATE TABLE bucket_assignment(
 bucket_id integer PRIMARY KEY CHECK(bucket_id BETWEEN 0 AND 255),
 owner_site_id text NOT NULL REFERENCES site_registry(site_id), ownership_epoch bigint NOT NULL DEFAULT 1,
 mapping_revision bigint NOT NULL DEFAULT 1, state text NOT NULL DEFAULT 'active'
 CHECK(state IN ('active','moving'))
);
CREATE TABLE seller_bucket(seller_id integer PRIMARY KEY REFERENCES user_core(user_id), bucket_id integer NOT NULL REFERENCES bucket_assignment(bucket_id));
CREATE TABLE catalogue_directory(
 product_id integer PRIMARY KEY, seller_id integer NOT NULL REFERENCES user_core(user_id),
 bucket_id integer NOT NULL REFERENCES bucket_assignment(bucket_id), lifecycle text NOT NULL DEFAULT 'pending'
 CHECK(lifecycle IN ('pending','active','deleted')), operation_id uuid NOT NULL UNIQUE,
 request_hash text, UNIQUE(product_id,seller_id)
);
CREATE TABLE global_id_allocator(entity text PRIMARY KEY,next_id bigint NOT NULL CHECK(next_id>0));
INSERT INTO global_id_allocator SELECT value,100000 FROM unnest(ARRAY['product','image','user','order','order_detail','review','contact']) value;
CREATE TABLE seed_runs(
 run_id uuid PRIMARY KEY, dataset_id text NOT NULL UNIQUE, dataset_hash text NOT NULL, plan jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending', phase text, error_code text, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE seed_entities(dataset_id text NOT NULL,entity text NOT NULL,logical_key text NOT NULL,
 global_id integer NOT NULL, content_hash text NOT NULL, PRIMARY KEY(dataset_id,entity,logical_key),UNIQUE(entity,global_id));
CREATE TABLE bucket_moves(
 operation_id uuid PRIMARY KEY,bucket_id integer NOT NULL,source_site text NOT NULL,target_site text NOT NULL,
 old_epoch bigint NOT NULL,state text NOT NULL,details jsonb NOT NULL DEFAULT '{}',updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX bucket_moves_open ON bucket_moves(bucket_id) WHERE state NOT IN ('complete','cancelled');
CREATE TABLE commerce_operation(
 operation_id uuid PRIMARY KEY,user_id integer NOT NULL REFERENCES user_core(user_id),kind text NOT NULL,
 request_hash text NOT NULL,state text NOT NULL,payload jsonb NOT NULL,result jsonb,
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE order_detail DROP CONSTRAINT order_detail_product_id_fkey;
ALTER TABLE order_detail ADD CONSTRAINT order_detail_directory_fk FOREIGN KEY(product_id) REFERENCES catalogue_directory(product_id);
ALTER TABLE shopping_cart_item DROP CONSTRAINT shopping_cart_item_product_id_fkey;
ALTER TABLE shopping_cart_item ADD CONSTRAINT cart_directory_fk FOREIGN KEY(product_id) REFERENCES catalogue_directory(product_id);
ALTER TABLE review DROP CONSTRAINT review_product_id_fkey;
ALTER TABLE review ADD CONSTRAINT review_directory_fk FOREIGN KEY(product_id) REFERENCES catalogue_directory(product_id);
ALTER TABLE shopping_cart_item ADD COLUMN reservation_id uuid, ADD CONSTRAINT cart_unique_product UNIQUE(cart_id,product_id);
ALTER TABLE order_detail ADD COLUMN product_snapshot jsonb, ADD COLUMN reservation_id uuid;
ALTER TABLE "order" ADD COLUMN operation_id uuid;
-- Hash-partitioned orders require order_id in unique indexes. Global request
-- uniqueness is enforced separately by commerce_operation.operation_id.
CREATE OR REPLACE FUNCTION check_no_self_buying() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM "order" o JOIN catalogue_directory p ON p.product_id=NEW.product_id
           WHERE o.order_id=NEW.order_id AND o.buyer_id=p.seller_id) THEN
   RAISE EXCEPTION 'BUSINESS_RULE_VIOLATION: Sellers cannot buy their own products.';
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION core_graph_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE row jsonb;
BEGIN
 row:=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
 PERFORM bucket_emit(TG_ARGV[0],(row->>TG_ARGV[1])::integer,TG_OP);
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE TRIGGER graph_order AFTER INSERT OR UPDATE ON "order" FOR EACH ROW EXECUTE FUNCTION core_graph_event('order','order_id');
CREATE TRIGGER graph_review AFTER INSERT OR UPDATE OR DELETE ON review FOR EACH ROW EXECUTE FUNCTION core_graph_event('review','review_id');
