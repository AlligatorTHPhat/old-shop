-- Separate site migration history; never applied to the commerce database.
-- __CONTRACT_SHA256__ is replaced by the release runner, not request input.
DO $$ BEGIN
    IF (SELECT count(*) FROM site_config) <> 1
       OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='product'::regclass
           AND tgname='enforce_product_site' AND tgenabled='O')
       OR NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='product_image'::regclass
           AND tgname='enforce_image_site' AND tgenabled='O')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='product'::regclass
           AND conname='product_seller_site_fkey' AND convalidated)
       OR EXISTS (SELECT 1 FROM pg_sequence WHERE seqrelid IN ('product_product_id_seq'::regclass,
           'product_image_image_id_seq'::regclass) AND seqincrement<>2)
       OR EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid IN ('product'::regclass,'product_image'::regclass)
           AND NOT convalidated)
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='product_image'::regclass
           AND contype='f' AND confrelid='product'::regclass AND convalidated)
    THEN RAISE EXCEPTION 'Fragment rules are missing or disabled'; END IF;
    IF EXISTS (SELECT 1 FROM product p LEFT JOIN seller_site s USING(seller_id)
        WHERE s.site_id IS DISTINCT FROM p.site_id OR p.site_id <> local_site()
           OR p.product_id <= 0 OR mod(p.product_id,2) <> (SELECT id_remainder FROM site_config))
       OR EXISTS (SELECT 1 FROM product_image i LEFT JOIN product p USING(product_id)
           WHERE p.product_id IS NULL OR i.image_id <= 0
               OR mod(i.image_id,2) <> (SELECT id_remainder FROM site_config))
    THEN RAISE EXCEPTION 'Existing fragment violates ownership or ID allocation'; END IF;
END $$;

CREATE FUNCTION fragment_rules_fingerprint() RETURNS text
LANGUAGE sql STABLE SET search_path=pg_catalog,public AS $$
    SELECT md5(COALESCE((SELECT string_agg(x.value,'|' ORDER BY x.value) FROM (
        SELECT pg_get_constraintdef(oid) || ':' || convalidated::text AS value
        FROM pg_constraint WHERE conrelid IN ('public.product'::regclass,'public.product_image'::regclass)
        UNION ALL
        SELECT tgname || ':' || tgenabled::text || ':' || pg_get_triggerdef(oid) || ':' || pg_get_functiondef(tgfoid)
        FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('public.product'::regclass,'public.product_image'::regclass)
        UNION ALL
        SELECT pg_get_functiondef('public.local_site()'::regprocedure)
    ) x),'') || ':' || COALESCE((SELECT string_agg(seqincrement::text,',' ORDER BY seqrelid::regclass::text)
        FROM pg_sequence WHERE seqrelid IN ('public.product_product_id_seq'::regclass,
            'public.product_image_image_id_seq'::regclass)),''))
$$;
CREATE TABLE fragment_contract_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    revision text NOT NULL CHECK(revision='fragmentation-v1'),
    contract_sha256 text NOT NULL CHECK(contract_sha256 ~ '^[0-9a-f]{64}$'),
    rules_fingerprint text NOT NULL,
    reference_sha256 text NOT NULL
);
CREATE FUNCTION fragment_reference_fingerprint() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    SELECT encode(digest(
        COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY category_id)::text FROM public.category r),'[]') || ':' ||
        COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY seller_id)::text FROM public.seller_site r),'[]'),
        'sha256'),'hex')
$$;
INSERT INTO fragment_contract_state VALUES
    (true,'fragmentation-v1','__CONTRACT_SHA256__',fragment_rules_fingerprint(),fragment_reference_fingerprint());

CREATE VIEW v_fragment_identity AS
    SELECT c.site_id,c.id_remainder,s.revision,s.contract_sha256,
        s.rules_fingerprint=fragment_rules_fingerprint()
            AND s.reference_sha256=fragment_reference_fingerprint() AS rules_valid,
        fragment_reference_fingerprint() AS reference_sha256
    FROM site_config c CROSS JOIN fragment_contract_state s;

-- Local projections are read-only for gateway credentials through grants.
CREATE VIEW v_local_product AS SELECT product_id,seller_id,category_id,title,description,price,
    quantity,status,view_count,created_at,updated_at,site_id,is_deleted FROM product;
CREATE VIEW v_local_category AS SELECT category_id,name,is_active,is_deleted FROM category;
CREATE VIEW v_local_product_image AS SELECT image_id,product_id,image_url,alt_text,is_primary,display_order
    FROM product_image;
CREATE VIEW v_local_seller_site AS SELECT seller_id,site_id FROM seller_site;
REVOKE ALL ON fragment_contract_state FROM PUBLIC,site_writer,b_reader,global_reader;
REVOKE ALL ON FUNCTION fragment_rules_fingerprint() FROM PUBLIC;
REVOKE ALL ON FUNCTION fragment_reference_fingerprint() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION fragment_rules_fingerprint() TO global_reader,b_reader;
GRANT EXECUTE ON FUNCTION fragment_reference_fingerprint() TO global_reader,b_reader;
GRANT SELECT ON v_fragment_identity TO global_reader,b_reader;
GRANT SELECT ON v_local_product,v_local_category,v_local_product_image,v_local_seller_site TO global_reader;
