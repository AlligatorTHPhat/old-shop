-- Indexing v2: selected from isolated PG16/Mongo8 measurements (2026-11-01).
-- Additive only: keep prior indexes/constraints until live usage can be observed.
-- I02: global catalogue order, including the existing ascending ID tie breaker.
CREATE INDEX idx_product_visible_date_id
    ON product(created_at DESC, product_id ASC)
    WHERE status = 1 AND is_deleted = FALSE;
-- I04/I05: cleanup must find shared references, including soft-deleted products.
-- URLs/avatars are deliberately NOT UNIQUE.
CREATE INDEX idx_product_image_url ON product_image(image_url);
CREATE INDEX idx_user_profile_avatar_url ON user_profile(avatar_url);
-- I07: voucher fan-out includes deleted orders; propagate through the HASH parent.
CREATE INDEX idx_order_voucher_lookup ON "order"(voucher_id);
-- I08/I09: latest operational run and latest successful aggregate.
CREATE INDEX idx_etl_runs_started ON etl_runs(started_at DESC);
CREATE INDEX idx_etl_runs_aggregate_success ON etl_runs(ended_at DESC)
    WHERE status = 'success' AND details ? 'aggregate';
-- I10: equality on the complete JSONB entity key, then the oldest pending event.
CREATE INDEX idx_etl_outbox_entity_pending ON etl_outbox(entity_type, entity_key, event_id)
    WHERE status <> 'done';
-- I11: retain the worker's event_id order and clock_timestamp() due-time semantics.
CREATE INDEX idx_etl_outbox_pending_event ON etl_outbox(event_id, available_at)
    WHERE status IN ('pending', 'dead');
-- I12: list members of a role; PK(user_id,role_id) remains the user-first path.
CREATE INDEX idx_user_role_role_user ON user_role(role_id, user_id);
