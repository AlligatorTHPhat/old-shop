CREATE TABLE payment_intent(
 order_id integer PRIMARY KEY REFERENCES "order"(order_id),request_id uuid NOT NULL UNIQUE,
 provider_id text UNIQUE,state text NOT NULL DEFAULT 'pending',provider_response jsonb,
 updated_at timestamptz NOT NULL DEFAULT now()
);
