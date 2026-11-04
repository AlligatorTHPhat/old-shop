SELECT p.product_id, p.title, c.name AS category_name, p.site_id
FROM v_product p JOIN v_category c USING (category_id)
WHERE NOT p.is_deleted ORDER BY p.product_id
