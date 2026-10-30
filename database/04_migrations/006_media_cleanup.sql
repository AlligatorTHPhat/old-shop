-- Durable deletion requests, in the same PG transaction as unlinking the image.
-- Product soft-delete retains images; this queue handles explicit image removal and replaced uploads.
CREATE TABLE media_deletions (
 deletion_id bigserial PRIMARY KEY,
 url_path text NOT NULL UNIQUE CHECK(url_path LIKE '/media/%'),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
 attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 processed_at timestamptz,
 last_error_code varchar(80)
);
CREATE INDEX idx_media_deletions_due ON media_deletions(available_at,deletion_id) WHERE status='pending';
CREATE FUNCTION queue_unlinked_media() RETURNS trigger LANGUAGE plpgsql SET search_path=public AS $$
DECLARE old_url text;
BEGIN
 IF TG_TABLE_NAME='product_image' THEN
  old_url:=OLD.image_url;
  IF TG_OP='UPDATE' AND NEW.image_url IS NOT DISTINCT FROM OLD.image_url THEN RETURN NEW; END IF;
 ELSE
  old_url:=OLD.avatar_url;
  IF NEW.avatar_url IS NOT DISTINCT FROM OLD.avatar_url THEN RETURN NEW; END IF;
  -- Seed/shared avatars are retained. Only immutable user uploads are collected automatically.
  IF old_url !~ '^/media/users/[0-9]+/avatar-[0-9a-f]{32}\.[a-z]+$' THEN RETURN NEW; END IF;
 END IF;
 IF old_url LIKE '/media/%' THEN
  INSERT INTO media_deletions(url_path) VALUES(old_url)
   ON CONFLICT(url_path) DO UPDATE SET status='pending',available_at=clock_timestamp(),
     processed_at=NULL,last_error_code=NULL;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER queue_product_image_cleanup AFTER DELETE OR UPDATE OF image_url ON product_image
 FOR EACH ROW EXECUTE FUNCTION queue_unlinked_media();
CREATE TRIGGER queue_avatar_cleanup AFTER UPDATE OF avatar_url ON user_profile
 FOR EACH ROW EXECUTE FUNCTION queue_unlinked_media();
