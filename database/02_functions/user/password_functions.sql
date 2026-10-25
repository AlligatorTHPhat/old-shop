-- =
-- PASSWORD FUNCTIONS
-- ==============================================================================
-- Functions for secure password management and user authentication
-- ==============================================================================

-- Function to hash password using bcrypt
-- Security: Uses blowfish algorithm with cost factor 8
-- Returns: Hashed password string
CREATE OR REPLACE FUNCTION hash_password(password TEXT)
RETURNS TEXT AS $$
DECLARE
    hashed_password TEXT;
BEGIN
    -- Validate input
    IF password IS NULL OR length(trim(password)) = 0 THEN
        RAISE EXCEPTION 'Password cannot be empty';
    END IF;

    IF length(password) < 6 THEN
        RAISE EXCEPTION 'Password must be at least 6 characters long';
    END IF;

    -- Hash the password
    hashed_password := crypt(password, gen_salt('bf', 8));

    RETURN hashed_password;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to verify password against hash
-- Returns: TRUE if password matches, FALSE otherwise
CREATE OR REPLACE FUNCTION verify_password(password TEXT, hashed_password TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    is_valid BOOLEAN := FALSE;
BEGIN
    -- Validate inputs
    IF password IS NULL OR hashed_password IS NULL THEN
        RETURN FALSE;
    END IF;

    -- Verify password
    IF crypt(password, hashed_password) = hashed_password THEN
        is_valid := TRUE;
    END IF;

    RETURN is_valid;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to generate cryptographically secure random key
-- Returns: 64-character hexadecimal string (256 bits)
CREATE OR REPLACE FUNCTION generate_random_key()
RETURNS TEXT AS $$
DECLARE
    random_key TEXT;
BEGIN
    -- Generate 32 bytes (256 bits) of random data
    random_key := encode(gen_random_bytes(32), 'hex');

    RETURN random_key;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to generate secure password reset token
-- Returns: URL-safe token
CREATE OR REPLACE FUNCTION generate_password_reset_token()
RETURNS TEXT AS $$
DECLARE
    token TEXT;
BEGIN
    -- Generate 32 bytes of random data, base64url encoded
    token := encode(gen_random_bytes(32), 'base64');
    -- Make URL-safe by replacing problematic characters
    token := replace(replace(token, '+', '-'), '/', '_');
    -- Remove padding
    token := rtrim(token, '=');

    RETURN token;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to create user with proper validation and security
-- Returns: New user ID
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
    IF EXISTS (SELECT 1 FROM "user" WHERE username = trim(p_username) AND is_deleted = FALSE) THEN
        RAISE EXCEPTION 'Username already exists';
    END IF;

    -- Check for existing email
    IF EXISTS (SELECT 1 FROM "user" WHERE email = trim(p_email) AND is_deleted = FALSE) THEN
        RAISE EXCEPTION 'Email already exists';
    END IF;

    -- Create user with hashed password
    INSERT INTO "user" (
        username,
        email,
        password_hash,
        random_key,
        full_name,
        phone_number,
        address,
        email_verified
    )
    VALUES (
        trim(p_username),
        trim(p_email),
        hash_password(p_password),
        generate_random_key(),
        trim(p_full_name),
        NULLIF(trim(p_phone_number), ''),
        NULLIF(trim(p_address), ''),
        FALSE
    )
    RETURNING user_id INTO new_user_id;

    -- Log user creation
    PERFORM log_system_action(new_user_id, 'USER_CREATED', 'user', new_user_id, 'User account created');

    RETURN new_user_id;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to authenticate user
-- Returns: User record if successful, raises exception if failed
CREATE OR REPLACE FUNCTION authenticate_user(p_username_or_email TEXT, p_password TEXT)
RETURNS TABLE (
    user_id INTEGER,
    username VARCHAR(50),
    email VARCHAR(100),
    full_name VARCHAR(100),
    is_active BOOLEAN,
    role_name VARCHAR(50)
) AS $$
DECLARE
    user_record RECORD;
    login_successful BOOLEAN := FALSE;
BEGIN
    -- Find user by username or email
    SELECT u.*, r.role_name INTO user_record
    FROM "user" u
    JOIN user_role ur ON u.user_id = ur.user_id
    JOIN role r ON ur.role_id = r.role_id
    WHERE (u.username = p_username_or_email OR u.email = p_username_or_email)
    AND u.is_deleted = FALSE;

    -- Check if user exists
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid username or password';
    END IF;

    -- Check if user is active
    IF NOT user_record.is_active THEN
        RAISE EXCEPTION 'Account is deactivated';
    END IF;

    -- Verify password
    IF verify_password(p_password, user_record.password_hash) THEN
        login_successful := TRUE;

        -- Update last login
        UPDATE "user" SET last_login = CURRENT_TIMESTAMP WHERE user_id = user_record.user_id;

        -- Log successful login
        PERFORM log_system_action(user_record.user_id, 'LOGIN_SUCCESS', 'user', user_record.user_id, 'Successful login');
    ELSE
        -- Log failed login attempt
        PERFORM log_system_action(user_record.user_id, 'LOGIN_FAILED', 'user', user_record.user_id, 'Failed login attempt');

        RAISE EXCEPTION 'Invalid username or password';
    END IF;

    -- Return user data
    RETURN QUERY
    SELECT
        user_record.user_id,
        user_record.username,
        user_record.email,
        user_record.full_name,
        user_record.is_active,
        user_record.role_name;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;