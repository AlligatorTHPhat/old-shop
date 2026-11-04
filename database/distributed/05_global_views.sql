CREATE OR REPLACE VIEW v_product AS
    SELECT product_id, seller_id, category_id, title, description, price, quantity,
        view_count, video_url, status, reject_reason, approved_by, is_deleted,
        created_at, updated_at, sold_at, weight_grams, dimensions, condition_rating,
        warranty_months, transfer_method, site_id FROM public.product
    UNION ALL
    SELECT product_id, seller_id, category_id, title, description, price, quantity,
        view_count, video_url, status, reject_reason, approved_by, is_deleted,
        created_at, updated_at, sold_at, weight_grams, dimensions, condition_rating,
        warranty_months, transfer_method, site_id FROM site_b.product;
CREATE OR REPLACE VIEW v_product_image AS
    SELECT image_id, product_id, image_url, alt_text, is_primary, display_order,
        uploaded_at, content_type, size_bytes FROM public.product_image
    UNION ALL
    SELECT image_id, product_id, image_url, alt_text, is_primary, display_order,
        uploaded_at, content_type, size_bytes FROM site_b.product_image;
CREATE OR REPLACE VIEW v_category AS
    SELECT category_id, name, description, parent_id, is_active, is_deleted, created_at, updated_at
    FROM public.category;
CREATE OR REPLACE VIEW v_seller_site AS SELECT seller_id, site_id FROM public.seller_site;
CREATE OR REPLACE VIEW v_site_health AS
    SELECT site_id FROM public.site_identity UNION ALL SELECT site_id FROM site_b.site_identity;
GRANT SELECT ON v_product, v_product_image, v_category, v_seller_site, site_identity TO global_reader;
GRANT SELECT ON v_site_health TO global_reader;
