-- Keep an exact transaction-local snapshot for lossless 20-column reconciliation.
CREATE TEMP TABLE day4_user_before ON COMMIT DROP AS SELECT * FROM "user";
ALTER TABLE "user" RENAME TO user_core;
-- Existing inbound FKs follow the relation OID automatically; do not drop CASCADE.
CREATE TABLE user_profile (
 user_id integer PRIMARY KEY REFERENCES user_core(user_id) ON DELETE CASCADE,
 full_name varchar(100) NOT NULL, phone_number varchar(15), address varchar(255), avatar_url varchar(500)
);
CREATE TABLE user_secret (
 user_id integer PRIMARY KEY REFERENCES user_core(user_id) ON DELETE CASCADE,
 password_hash varchar(255) NOT NULL, random_key varchar(64) NOT NULL UNIQUE,
 email_verification_token varchar(255), password_reset_token varchar(255), password_reset_expires timestamp
);
CREATE TABLE user_wallet (
 user_id integer PRIMARY KEY REFERENCES user_core(user_id) ON DELETE CASCADE,
 balance numeric(18,4) NOT NULL DEFAULT 10000000.00
);
INSERT INTO user_profile SELECT user_id,full_name,phone_number,address,avatar_url FROM user_core;
INSERT INTO user_secret SELECT user_id,password_hash,random_key,email_verification_token,password_reset_token,password_reset_expires FROM user_core;
INSERT INTO user_wallet SELECT user_id,balance FROM user_core;
ALTER TABLE user_core
 DROP COLUMN password_hash, DROP COLUMN random_key, DROP COLUMN full_name,
 DROP COLUMN phone_number, DROP COLUMN address, DROP COLUMN balance,
 DROP COLUMN email_verification_token, DROP COLUMN password_reset_token,
 DROP COLUMN password_reset_expires, DROP COLUMN avatar_url;
CREATE VIEW users_full AS SELECT
 c.user_id,c.username,c.email,s.password_hash,s.random_key,p.full_name,p.phone_number,p.address,w.balance,
 c.is_active,c.is_deleted,c.created_at,c.updated_at,c.last_login,c.email_verified,s.email_verification_token,
 s.password_reset_token,s.password_reset_expires,c.trust_score,p.avatar_url
 FROM user_core c JOIN user_profile p USING(user_id) JOIN user_secret s USING(user_id) JOIN user_wallet w USING(user_id);
-- This join view is deliberately read-only. No INSTEAD OF write triggers.
REVOKE ALL ON users_full FROM PUBLIC;
REVOKE ALL ON user_secret, user_wallet FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS ((SELECT * FROM day4_user_before EXCEPT ALL SELECT * FROM users_full)
   UNION ALL (SELECT * FROM users_full EXCEPT ALL SELECT * FROM day4_user_before)) THEN
   RAISE EXCEPTION 'User split reconciliation failed';
 END IF;
END $$;
-- Read functions switch to users_full; identity-only audit joins use user_core.
DO $$ DECLARE f record; definition text; BEGIN
 FOR f IN SELECT oid,proname FROM pg_proc WHERE pronamespace='public'::regnamespace
   AND proname IN ('authenticate_user','log_user_login','get_audit_trail') LOOP
  definition := pg_get_functiondef(f.oid);
  definition := replace(definition, 'FROM "user" u', 'FROM users_full u');
  definition := replace(definition, 'JOIN "user" u', 'JOIN user_core u');
  definition := replace(definition, 'UPDATE "user"', 'UPDATE user_core');
  -- Qualify UPDATE target to avoid authenticate_user output-variable ambiguity.
  definition := replace(definition, 'WHERE user_id = user_record.user_id', 'WHERE user_core.user_id = user_record.user_id');
  EXECUTE definition;
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION create_user_with_hash(
    p_username VARCHAR(50),
    p_email VARCHAR(100),
    p_password TEXT,
    p_full_name VARCHAR(100),
    p_phone_number VARCHAR(15) DEFAULT NULL,
    p_address VARCHAR(255) DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    new_user_id INTEGER;
    email_regex TEXT := '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$';
BEGIN
    -- Validate inputs
    IF p_username IS NULL OR length(trim(p_username)) = 0 THEN
        RAISE EXCEPTION 'Username cannot be empty';
    END IF;

    IF p_email IS NULL OR length(trim(p_email)) = 0 THEN
        RAISE EXCEPTION 'Email cannot be empty';
    END IF;

    IF p_full_name IS NULL OR length(trim(p_full_name)) = 0 THEN
        RAISE EXCEPTION 'Full name cannot be empty';
    END IF;

    -- Validate email format
    IF NOT (p_email ~ email_regex) THEN
        RAISE EXCEPTION 'Invalid email format';
    END IF;

    -- Check for existing username
    IF EXISTS (SELECT 1 FROM user_core WHERE username = trim(p_username) AND is_deleted = FALSE) THEN
        RAISE EXCEPTION 'Username already exists';
    END IF;

    -- Check for existing email
    IF EXISTS (SELECT 1 FROM user_core WHERE email = trim(p_email) AND is_deleted = FALSE) THEN
        RAISE EXCEPTION 'Email already exists';
    END IF;

    INSERT INTO user_core(username,email,email_verified)
    VALUES(trim(p_username),trim(p_email),FALSE) RETURNING user_id INTO new_user_id;
    INSERT INTO user_profile(user_id,full_name,phone_number,address)
    VALUES(new_user_id,trim(p_full_name),NULLIF(trim(p_phone_number),''),NULLIF(trim(p_address),''));
    INSERT INTO user_secret(user_id,password_hash,random_key)
    VALUES(new_user_id,hash_password(p_password),generate_random_key());
    INSERT INTO user_wallet(user_id) VALUES(new_user_id);

    -- Log user creation
    PERFORM log_system_action(new_user_id, 'USER_CREATED', 'user', new_user_id, 'User account created');

    RETURN new_user_id;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

