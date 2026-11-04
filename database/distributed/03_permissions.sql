-- Role passwords are assigned by the orchestrator using SQL literals on stdin.
REVOKE ALL ON DATABASE :"target_db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"target_db" TO site_writer, b_reader, global_reader;
GRANT USAGE ON SCHEMA public TO site_writer, b_reader, global_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON product, product_image TO site_writer;
GRANT SELECT ON category, seller_site, site_identity TO site_writer;
GRANT USAGE, SELECT ON SEQUENCE product_product_id_seq, product_image_image_id_seq TO site_writer;
GRANT EXECUTE ON FUNCTION local_site() TO site_writer;
GRANT SELECT ON product, product_image, category, seller_site, site_identity TO b_reader;
