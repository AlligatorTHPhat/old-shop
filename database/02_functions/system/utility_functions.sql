-- =
-- UTILITY FUNCTIONS
-- ==============================================================================
-- General utility functions for common operations
-- ==============================================================================

-- Function to generate transaction code
-- Format: TXN_YYYYMMDD_HHMMSS_RRRR (R = random digits)
CREATE OR REPLACE FUNCTION generate_transaction_code()
RETURNS TEXT AS $$
DECLARE
    timestamp_part TEXT;
    random_part TEXT;
BEGIN
    -- Get timestamp part
    timestamp_part := TO_CHAR(CURRENT_TIMESTAMP, 'YYYYMMDD_HH24MISS');

    -- Generate 4 random digits
    random_part := LPAD(FLOOR(RANDOM() * 10000)::TEXT, 4, '0');

    RETURN 'TXN_' || timestamp_part || '_' || random_part;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;

-- Function to format currency (VND)
CREATE OR REPLACE FUNCTION format_currency(amount DECIMAL(18,2))
RETURNS TEXT AS $$
BEGIN
    RETURN TO_CHAR(amount, 'FM999,999,999,990') || ' VND';
END;
$$ LANGUAGE plpgsql
IMMUTABLE
SECURITY DEFINER
SET search_path = public;

-- Function to calculate percentage
CREATE OR REPLACE FUNCTION calculate_percentage(part DECIMAL, total DECIMAL)
RETURNS DECIMAL(5,2) AS $$
BEGIN
    IF total = 0 THEN
        RETURN 0;
    END IF;
    RETURN ROUND((part / total * 100)::DECIMAL(5,2), 2);
END;
$$ LANGUAGE plpgsql
IMMUTABLE
SECURITY DEFINER
SET search_path = public;

-- Function to get current database statistics
CREATE OR REPLACE FUNCTION get_database_stats()
RETURNS TABLE (
    table_name TEXT,
    row_count BIGINT,
    size_pretty TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.table_name::TEXT,
        c.row_count,
        pg_size_pretty(pg_total_relation_size(t.table_schema || '.' || t.table_name))::TEXT
    FROM information_schema.tables t
    LEFT JOIN (
        SELECT schemaname, tablename, n_tup_ins - n_tup_del as row_count
        FROM pg_stat_user_tables
    ) c ON t.table_schema = c.schemaname AND t.table_name = c.tablename
    WHERE t.table_schema = 'public'
    AND t.table_type = 'BASE TABLE'
    ORDER BY c.row_count DESC NULLS LAST;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public;