-- Day 1 baseline verification on a throwaway database loaded with init.sql.
-- Run with psql -X -v ON_ERROR_STOP=1 -f verify_day1.sql, or in pgAdmin Query Tool.
-- Changes are rolled back; sequence nextval() calls can still consume IDs.
BEGIN;
SET LOCAL timezone = 'Asia/Ho_Chi_Minh';

SELECT version() AS postgres_version, current_database() AS database;
SELECT extname, extversion FROM pg_extension ORDER BY extname;

DO $$
DECLARE
    table_count integer;
    column_count integer;
    trigger_count integer;
    expected record;
    actual bigint;
BEGIN
    SELECT count(*) INTO table_count FROM pg_tables WHERE schemaname = 'public';
    SELECT count(*) INTO column_count FROM information_schema.columns WHERE table_schema = 'public';
    SELECT count(*) INTO trigger_count FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND NOT t.tgisinternal;
    IF (table_count, column_count, trigger_count) IS DISTINCT FROM (18, 167, 2) THEN
        RAISE EXCEPTION 'Unexpected baseline: tables %, columns %, triggers %',
          table_count, column_count, trigger_count;
    END IF;
    FOR expected IN SELECT * FROM (VALUES
      ('role',3), ('user',15), ('user_role',15), ('category',8),
      ('product',16), ('product_image',32), ('voucher',4), ('payment_method',5),
      ('contact_info',15), ('order',30), ('order_detail',30), ('transaction',30),
      ('shopping_cart',11), ('shopping_cart_item',0), ('review',0),
      ('system_log',0), ('system_feedback',0), ('violation_log',11)
    ) AS counts(table_name, row_count) LOOP
        EXECUTE format('SELECT count(*) FROM public.%I', expected.table_name) INTO actual;
        IF actual <> expected.row_count THEN
            RAISE EXCEPTION 'Seed count %: expected %, got %',
              expected.table_name, expected.row_count, actual;
        END IF;
        RAISE NOTICE 'PASS seed % = %', expected.table_name, actual;
    END LOOP;
    RAISE NOTICE 'PASS baseline: 18 tables, 167 columns, 2 triggers';
END $$;

-- Catalog counts include PK/UNIQUE backing indexes, not just explicit CREATE INDEX.
SELECT contype, count(*) FROM pg_constraint k
JOIN pg_namespace n ON n.oid = k.connamespace
WHERE n.nspname = 'public' AND k.conrelid <> 0 GROUP BY contype ORDER BY contype;
SELECT count(*) AS total_indexes FROM pg_indexes WHERE schemaname = 'public';
SELECT transaction_status, count(*) FROM transaction GROUP BY transaction_status ORDER BY transaction_status;
SELECT count(*) AS orders_using_another_users_contact
FROM "order" o JOIN contact_info c ON c.contact_id = o.contact_id WHERE c.user_id <> o.buyer_id;

DO $$
DECLARE
    buyer integer;
    seller integer;
    pid integer;
    oid integer;
    qty integer;
    status_after smallint;
    old_updated timestamp;
    new_updated timestamp;
    old_log_count bigint;
    new_log_count bigint;
    did_block boolean := false;
BEGIN
    SELECT product_id, seller_id INTO pid, seller FROM product WHERE quantity > 0 ORDER BY product_id LIMIT 1;
    SELECT user_id INTO buyer FROM "user" WHERE user_id <> seller ORDER BY user_id LIMIT 1;
    SELECT quantity, updated_at INTO qty, old_updated FROM product WHERE product_id = pid;
    INSERT INTO "order" (buyer_id, contact_id, payment_method_id, total_amount, final_amount)
      SELECT seller, contact_id, 1, 100, 100 FROM contact_info WHERE user_id = seller LIMIT 1
      RETURNING order_id INTO oid;
    SELECT count(*) INTO old_log_count FROM system_log WHERE action = 'SELF_BUY_BLOCKED';
    BEGIN
        INSERT INTO order_detail(order_id,product_id,quantity,price_at_purchase,subtotal)
          VALUES(oid,pid,1,100,100);
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM NOT LIKE 'BUSINESS_RULE_VIOLATION:%' THEN RAISE; END IF;
        did_block := true;
    END;
    IF NOT did_block THEN RAISE EXCEPTION 'Self-buying trigger failed'; END IF;
    SELECT count(*) INTO new_log_count FROM system_log WHERE action = 'SELF_BUY_BLOCKED';
    IF new_log_count <> old_log_count THEN RAISE EXCEPTION 'Unexpected committed rejected-action log'; END IF;
    RAISE NOTICE 'PASS self-buy blocked; its transactional audit log rolls back';

    UPDATE "order" SET buyer_id = buyer WHERE order_id = oid;
    INSERT INTO order_detail(order_id,product_id,quantity,price_at_purchase,subtotal)
      VALUES(oid,pid,1,100,100);
    IF (SELECT quantity FROM product WHERE product_id = pid) <> qty THEN
        RAISE EXCEPTION 'Order-detail insert unexpectedly changed stock';
    END IF;
    RAISE NOTICE 'PASS order_detail insert does not reserve/decrement stock';

    UPDATE product SET title = title || ' [audit]' WHERE product_id = pid;
    SELECT updated_at INTO new_updated FROM product WHERE product_id = pid;
    IF new_updated IS DISTINCT FROM old_updated THEN
        RAISE EXCEPTION 'Unexpected timestamp change for raw title UPDATE';
    END IF;
    UPDATE product SET quantity = 0 WHERE product_id = pid;
    SELECT status INTO status_after FROM product WHERE product_id = pid;
    IF status_after <> 3 OR (SELECT sold_at IS NULL FROM product WHERE product_id = pid) THEN
        RAISE EXCEPTION 'Sold-out trigger failed';
    END IF;
    UPDATE product SET quantity = qty WHERE product_id = pid;
    IF (SELECT status FROM product WHERE product_id = pid) <> 3 THEN
        RAISE EXCEPTION 'Unexpected automatic status restoration';
    END IF;
    RAISE NOTICE 'PASS quantity=0 marks SOLD_OUT; raw restock does not restore APPROVED';
    RAISE NOTICE 'PASS raw title UPDATE does not refresh product.updated_at';

    BEGIN
        UPDATE product SET quantity = -1 WHERE product_id = pid;
        RAISE EXCEPTION 'Negative quantity unexpectedly accepted';
    EXCEPTION WHEN check_violation THEN
        RAISE NOTICE 'PASS negative quantity rejected by CHECK';
    END;
    INSERT INTO review(product_id,buyer_id,rating) VALUES(pid,buyer,0);
    RAISE NOTICE 'PASS rating=0 accepted as report';
    INSERT INTO transaction(order_id,user_id,payment_method_id,amount,reference_number)
      VALUES(oid,buyer,1,100,NULL),(oid,buyer,1,100,NULL);
    RAISE NOTICE 'PASS reference_number is nullable and UNIQUE permits multiple NULLs';
END $$;

-- Confirm a known latent function error without leaving voucher/order changes.
DO $$
DECLARE
    vid integer;
    oid integer;
BEGIN
    UPDATE voucher SET valid_to = CURRENT_TIMESTAMP + interval '1 day', valid_from = CURRENT_TIMESTAMP - interval '1 day'
      WHERE code = 'SAVE10' RETURNING voucher_id INTO vid;
    SELECT order_id INTO oid FROM "order" WHERE voucher_id IS NULL ORDER BY order_id LIMIT 1;
    IF vid IS NULL OR oid IS NULL THEN RAISE EXCEPTION 'Expected seed voucher/order missing'; END IF;
    BEGIN
        PERFORM apply_voucher_to_order(oid, 'SAVE10'::varchar);
        RAISE EXCEPTION 'Expected undefined updated_at column was not detected';
    EXCEPTION WHEN undefined_column THEN
        IF SQLERRM NOT LIKE '%updated_at%' THEN RAISE; END IF;
        RAISE NOTICE 'PASS known defect reproduced: apply_voucher_to_order references absent updated_at';
    END;
END $$;

ROLLBACK;
