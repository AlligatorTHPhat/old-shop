SELECT s.seller_id, s.site_id FROM v_seller_site s
WHERE NOT EXISTS (
    SELECT 1 FROM v_product p WHERE p.seller_id = s.seller_id AND NOT p.is_deleted
        AND p.created_at >= :'from_date'::timestamp AND p.created_at < :'to_date'::timestamp
) ORDER BY s.seller_id
