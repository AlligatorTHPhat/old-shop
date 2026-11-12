-- Run at A after both sites have installed migration 001_fragment_contract.
DO $$ BEGIN
    IF to_regclass('site_b.v_fragment_identity') IS NULL THEN
        IMPORT FOREIGN SCHEMA public LIMIT TO (v_fragment_identity) FROM SERVER server_b INTO site_b;
    END IF;
END $$;
CREATE OR REPLACE VIEW v_remote_fragment_identity AS SELECT * FROM site_b.v_fragment_identity;
CREATE OR REPLACE VIEW v_remote_product AS SELECT product_id,seller_id,category_id,title,description,price,
    quantity,status,view_count,created_at,updated_at,site_id,is_deleted FROM site_b.product;
CREATE OR REPLACE VIEW v_remote_category AS SELECT category_id,name,is_active,is_deleted FROM site_b.category;
CREATE OR REPLACE VIEW v_remote_product_image AS SELECT image_id,product_id,image_url,alt_text,is_primary,display_order
    FROM site_b.product_image;
GRANT SELECT ON v_remote_fragment_identity,v_remote_product,v_remote_category,v_remote_product_image TO global_reader;
