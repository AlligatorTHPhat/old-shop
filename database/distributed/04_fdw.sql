-- psql parameters: b_host, b_port, b_db, reader_pw, admin_role.
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
CREATE SERVER server_b FOREIGN DATA WRAPPER postgres_fdw OPTIONS (
    host :'b_host', port :'b_port', dbname :'b_db',
    connect_timeout '3', application_name 'oldshop-site-a'
);
CREATE USER MAPPING FOR :"admin_role" SERVER server_b
    OPTIONS (user 'b_reader', password :'reader_pw');
CREATE SCHEMA site_b;
IMPORT FOREIGN SCHEMA public LIMIT TO (product, product_image, category, seller_site, site_identity)
    FROM SERVER server_b INTO site_b;
REVOKE ALL ON SCHEMA site_b FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA site_b FROM PUBLIC;
