-- File bytes remain in MinIO/local storage; query metadata from PG without listing buckets.
-- Existing/external references remain nullable until an explicit stat-based backfill.
ALTER TABLE product_image ADD COLUMN content_type varchar(100);
ALTER TABLE product_image ADD COLUMN size_bytes bigint CHECK(size_bytes >= 0);
