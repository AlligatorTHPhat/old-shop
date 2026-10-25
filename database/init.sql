-- init_db.sql
-- Main initialization file for OldShop PostgreSQL database
-- Version: 2.0.0 - Enhanced with security, performance, and monitoring
-- Run this file to set up the entire database

-- Create database if not exists (run this manually if needed)
-- CREATE DATABASE oldshop;

-- Connect to the database
-- \c oldshop;

-- Database configuration (performance, security, extensions)
\i config/database_config.sql

-- Execute schema files in order (with indexes and constraints)
\i 01_schema/roles.sql
\i 01_schema/users.sql
\i 01_schema/user_roles.sql
\i 01_schema/categories.sql
\i 01_schema/products.sql
\i 01_schema/product_images.sql
\i 01_schema/vouchers.sql
\i 01_schema/payment_methods.sql
\i 01_schema/contact_info.sql
\i 01_schema/orders.sql
\i 01_schema/order_details.sql
\i 01_schema/transactions.sql
\i 01_schema/shopping_carts.sql
\i 01_schema/shopping_cart_items.sql
\i 01_schema/reviews.sql
\i 01_schema/system_logs.sql
\i 01_schema/system_feedback.sql
\i 01_schema/violation_logs.sql

-- Execute functions and triggers (business logic and security)
\i 02_functions/user/password_functions.sql
\i 02_functions/order_detail/triggers.sql
\i 02_functions/system/audit_functions.sql
\i 02_functions/system/business_functions.sql
\i 02_functions/system/utility_functions.sql

-- Execute seed data (with encrypted passwords and rich sample data)
\i 03_seeds/role/seed.sql
\i 03_seeds/category/seed.sql
\i 03_seeds/payment_method/seed.sql
\i 03_seeds/voucher/seed.sql
\i 03_seeds/user/seed.sql
\i 03_seeds/product/seed.sql
\i 03_seeds/product_images/seed.sql
\i 03_seeds/contact_info/seed.sql
\i 03_seeds/shopping_cart/seed.sql
\i 03_seeds/order/seed.sql
\i 03_seeds/violation_logs/seed.sql

-- Final setup: Analyze tables for query optimization
ANALYZE;

-- Display setup completion message
DO $$
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'OldShop Database Setup Completed Successfully!';
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Version: 2.0.0';
    RAISE NOTICE 'Features: Security, Performance, Monitoring';
    RAISE NOTICE 'Default admin: admin@oldshop.com / admin123';
    RAISE NOTICE '================================================';
END $$;