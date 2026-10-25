-- database_config.sql
-- Session-level settings and extensions required by the schema.
--
-- Server tuning (shared_buffers, autovacuum, logging...) is intentionally NOT
-- done here with ALTER SYSTEM: an init script must never rewrite the config of
-- whatever server it runs against. In Docker the values are passed as
-- `postgres -c ...` flags, see deploy/docker-compose.yml.

SET timezone = 'Asia/Ho_Chi_Minh';
SET client_encoding = 'UTF8';
SET search_path TO public;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- text search
