CREATE TABLE IF NOT EXISTS stock_operation(
 operation_id uuid PRIMARY KEY,request_hash text NOT NULL,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
