SELECT c.category_id, c.name, count(p.product_id) AS product_count
FROM v_category c LEFT JOIN v_product p ON p.category_id = c.category_id AND NOT p.is_deleted
GROUP BY c.category_id, c.name ORDER BY c.category_id
