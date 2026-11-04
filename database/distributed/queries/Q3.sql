SELECT p.product_id, p.title, p.site_id, i.image_id, i.image_url
FROM v_product p LEFT JOIN v_product_image i USING (product_id)
WHERE p.product_id = :'product_id'::integer ORDER BY i.image_id
