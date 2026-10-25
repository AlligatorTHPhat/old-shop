-- =
-- AUDIT FUNCTIONS
-- ==============================================================================
-- Functions for comprehensive system logging and auditing
-- ==============================================================================

-- Function to log system actions with detailed information
-- Parameters:
--   p_user_id: ID of user performing action (can be NULL for system actions)
--   p_action_type: Type of action (LOGIN, CREATE, UPDATE, DELETE, etc.)
--   p_table_name: Table affected by the action
--   p_record_id: ID of the record affected
--   p_description: Detailed description of the action
CREATE OR REPLACE FUNCTION log_system_action(
    p_user_id INT DEFAULT NULL,
    p_action_type VARCHAR(50) DEFAULT 'UNKNOWN',
    p_table_name VARCHAR(50) DEFAULT 'unknown',
    p_record_id INT DEFAULT NULL,
    p_description TEXT DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    client_ip INET;
    user_agent TEXT;
BEGIN
    -- Get client information from session variables if available
    BEGIN
        client_ip := inet_client_addr();
        user_agent := current_setting('request.header.user-agent', TRUE);
    EXCEPTION
        WHEN OTHERS THEN
            client_ip := NULL;
            user_agent := NULL;
    END;

    -- Insert audit log
    INSERT INTO system_log (
        user_id,
        action,
        resource_type,
        resource_id,
        details,
        ip_address,
        created_at
    )
    VALUES (
        p_user_id,
        UPPER(trim(p_action_type)),
        LOWER(trim(p_table_name)),
        p_record_id,
        CASE
            WHEN p_description IS NOT NULL THEN trim(p_description)
            WHEN client_ip IS NOT NULL THEN 'IP: ' || client_ip::TEXT
            ELSE 'System action'
        END,
        client_ip::VARCHAR(45),
        CURRENT_TIMESTAMP
    );
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to log user login events
-- Automatically updates last_login timestamp
CREATE OR REPLACE FUNCTION log_user_login(
    p_user_id INT,
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    login_description TEXT;
BEGIN
    -- Update last login timestamp
    UPDATE "user"
    SET last_login = CURRENT_TIMESTAMP
    WHERE user_id = p_user_id AND is_deleted = FALSE;

    -- Build login description
    login_description := 'User login';
    IF p_ip_address IS NOT NULL THEN
        login_description := login_description || ' from IP: ' || p_ip_address::TEXT;
    END IF;
    IF p_user_agent IS NOT NULL THEN
        login_description := login_description || ' using: ' || substring(p_user_agent, 1, 100);
    END IF;

    -- Log the login event
    PERFORM log_system_action(p_user_id, 'LOGIN', 'user', p_user_id, login_description);
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to log user logout events
CREATE OR REPLACE FUNCTION log_user_logout(p_user_id INT)
RETURNS VOID AS $$
BEGIN
    PERFORM log_system_action(p_user_id, 'LOGOUT', 'user', p_user_id, 'User logout');
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Generic audit trigger function for any table
-- Automatically logs INSERT, UPDATE, DELETE operations
-- Note: This function assumes tables have a primary key column named 'id'
-- For tables with different PK names, create specific triggers
CREATE OR REPLACE FUNCTION generic_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
    action_type VARCHAR(10);
    record_id INT;
    change_description TEXT;
BEGIN
    -- Determine action type
    IF TG_OP = 'INSERT' THEN
        action_type := 'INSERT';
        record_id := NEW.id;
        change_description := 'Record created';
    ELSIF TG_OP = 'UPDATE' THEN
        action_type := 'UPDATE';
        record_id := NEW.id;
        change_description := 'Record updated';
    ELSIF TG_OP = 'DELETE' THEN
        action_type := 'DELETE';
        record_id := OLD.id;
        change_description := 'Record deleted';
    ELSE
        RETURN COALESCE(NEW, OLD);
    END IF;

    -- Log the change (user_id will be NULL for system/auto operations)
    PERFORM log_system_action(NULL, action_type, TG_TABLE_NAME, record_id, change_description);

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to get audit trail for a specific record
-- Returns: Table of audit log entries for the specified record
CREATE OR REPLACE FUNCTION get_audit_trail(
    p_table_name VARCHAR(50),
    p_record_id INT,
    p_limit INT DEFAULT 50
)
RETURNS TABLE (
    log_id BIGINT,
    user_id INT,
    username VARCHAR(50),
    action_type VARCHAR(100),
    description TEXT,
    log_time TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sl.log_id,
        sl.user_id,
        u.username,
        sl.action,
        sl.details,
        sl.created_at
    FROM system_log sl
    LEFT JOIN "user" u ON sl.user_id = u.user_id
    WHERE sl.resource_type = LOWER(trim(p_table_name))
    AND sl.resource_id = p_record_id
    ORDER BY sl.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to clean old audit logs (for maintenance)
-- Parameters:
--   p_days_old: Delete logs older than this many days (default 90)
CREATE OR REPLACE FUNCTION clean_old_audit_logs(p_days_old INT DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete old logs
    DELETE FROM system_log
    WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * p_days_old;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Log the cleanup operation
    PERFORM log_system_action(
        NULL,
        'MAINTENANCE',
        'system_log',
        NULL,
        'Cleaned ' || deleted_count || ' audit log entries older than ' || p_days_old || ' days'
    );

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;