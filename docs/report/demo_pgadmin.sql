-- Ngày 7: SQL thuần cho pgAdmin4 Query Tool (PostgreSQL 16).
-- Chỉ đọc. Kết nối primary; không chạy init.sql vào DB đã có dữ liệu.
SELECT version(), current_database(), pg_is_in_recovery();
SELECT version, applied_at, checksum FROM schema_migrations ORDER BY version;
SELECT relid::regclass AS relation, parentrelid::regclass AS parent,
       isleaf, level FROM pg_partition_tree('public."order"'::regclass);
SELECT relid::regclass AS relation, parentrelid::regclass AS parent,
       isleaf, level FROM pg_partition_tree('public.system_log'::regclass);
SELECT tableoid::regclass AS physical_partition, count(*)
FROM "order" GROUP BY tableoid ORDER BY 1;
SELECT count(*) AS reconstructed_users FROM users_full;
SELECT (SELECT count(*) FROM user_core) AS core,
       (SELECT count(*) FROM user_profile) AS profile,
       (SELECT count(*) FROM user_secret) AS secret_count,
       (SELECT count(*) FROM user_wallet) AS wallet_count;
SELECT application_name, state, sync_state FROM pg_stat_replication;
EXPLAIN (ANALYZE, BUFFERS) SELECT order_id,order_status
FROM "order" WHERE order_id=1;
EXPLAIN (ANALYZE, BUFFERS) SELECT count(*) FROM system_log
WHERE created_at >= timestamp '2026-10-01' AND created_at < timestamp '2026-11-01';
SELECT status, count(*) FROM etl_outbox GROUP BY status;
SELECT mode,status,rows_in,rows_out,errors,started_at,ended_at
FROM etl_runs ORDER BY started_at DESC LIMIT 5;
SELECT report_date,seller_id,category_id,gross_sales_vnd,refreshed_at
FROM report_daily_sales ORDER BY report_date,seller_id,category_id;
-- Trên connection PG replica: phải trả true, không chạy lệnh ghi.
-- SELECT pg_is_in_recovery(),pg_last_wal_replay_lsn();
