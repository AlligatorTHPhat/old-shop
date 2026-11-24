CREATE TABLE order_fulfillment(
 order_id integer NOT NULL REFERENCES "order"(order_id),seller_id integer NOT NULL REFERENCES user_core(user_id),
 bucket_id integer NOT NULL REFERENCES bucket_assignment(bucket_id),status smallint NOT NULL DEFAULT 0 CHECK(status BETWEEN 0 AND 4),
 PRIMARY KEY(order_id,seller_id)
);
INSERT INTO order_fulfillment(order_id,seller_id,bucket_id,status)
 SELECT DISTINCT d.order_id,p.seller_id,p.bucket_id,o.order_status FROM order_detail d
 JOIN catalogue_directory p USING(product_id) JOIN "order" o USING(order_id);
CREATE FUNCTION reference_bucket_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM bucket_emit(TG_ARGV[0],(to_jsonb(NEW)->>TG_ARGV[1])::integer,TG_OP);
 RETURN NEW;
END $$;
CREATE TRIGGER category_bucket_event AFTER UPDATE ON category FOR EACH ROW EXECUTE FUNCTION reference_bucket_event('category','category_id');
CREATE TRIGGER user_bucket_event AFTER UPDATE OF username,is_active,is_deleted ON user_core
 FOR EACH ROW EXECUTE FUNCTION reference_bucket_event('user','user_id');
