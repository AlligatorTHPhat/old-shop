-- Apply only to a new, empty-data schema built from the repository SQL sources.
-- The same definitions are installed on both independent sites.
CREATE TABLE site_config (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    site_id text NOT NULL UNIQUE CHECK (site_id IN ('A', 'B')),
    id_remainder smallint NOT NULL,
    CHECK ((site_id = 'A' AND id_remainder = 1) OR (site_id = 'B' AND id_remainder = 0))
);
CREATE TABLE distributed_installation (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    version integer NOT NULL,
    source_sha256 text NOT NULL,
    fixture_version integer NOT NULL
);
CREATE TABLE seller_site (
    seller_id integer PRIMARY KEY REFERENCES user_core(user_id),
    site_id text NOT NULL CHECK (site_id IN ('A', 'B')),
    UNIQUE (seller_id, site_id)
);
CREATE FUNCTION local_site() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$ SELECT site_id FROM public.site_config WHERE singleton $$;

ALTER TABLE product ADD COLUMN site_id text NOT NULL DEFAULT local_site()
    CHECK (site_id IN ('A', 'B'));
ALTER TABLE product ADD CONSTRAINT product_seller_site_fkey
    FOREIGN KEY (seller_id, site_id) REFERENCES seller_site(seller_id, site_id);

CREATE FUNCTION enforce_product_site() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE config public.site_config%ROWTYPE;
BEGIN
    SELECT * INTO STRICT config FROM public.site_config WHERE singleton;
    IF NEW.site_id <> config.site_id THEN
        RAISE EXCEPTION 'product_wrong_site' USING ERRCODE = '23514';
    END IF;
    IF NEW.product_id <= 0 OR mod(NEW.product_id, 2) <> config.id_remainder THEN
        RAISE EXCEPTION 'product_wrong_id_allocation' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (NEW.product_id, NEW.seller_id, NEW.site_id)
        IS DISTINCT FROM (OLD.product_id, OLD.seller_id, OLD.site_id) THEN
        RAISE EXCEPTION 'product_ownership_immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER enforce_product_site BEFORE INSERT OR UPDATE ON product
    FOR EACH ROW EXECUTE FUNCTION enforce_product_site();

CREATE FUNCTION enforce_image_site() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
DECLARE remainder smallint;
BEGIN
    SELECT id_remainder INTO STRICT remainder FROM public.site_config WHERE singleton;
    IF NEW.image_id <= 0 OR mod(NEW.image_id, 2) <> remainder THEN
        RAISE EXCEPTION 'image_wrong_id_allocation' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (NEW.image_id, NEW.product_id) IS DISTINCT FROM (OLD.image_id, OLD.product_id) THEN
        RAISE EXCEPTION 'image_ownership_immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER enforce_image_site BEFORE INSERT OR UPDATE ON product_image
    FOR EACH ROW EXECUTE FUNCTION enforce_image_site();

CREATE VIEW site_identity AS SELECT site_id, id_remainder FROM site_config;

-- Writers emit events/cleanup requests through existing triggers without direct
-- grants to the operational tables. Public cannot create objects in this schema.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER FUNCTION etl_capture_change() SECURITY DEFINER;
ALTER FUNCTION queue_unlinked_media() SECURITY DEFINER;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
-- Baseline SECURITY DEFINER business/auth functions must not be callable by readers.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
