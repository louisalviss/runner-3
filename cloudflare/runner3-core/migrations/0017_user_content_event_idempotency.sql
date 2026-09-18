-- Enforce the event identity already used by application-level idempotency guards.
-- Production preflight must confirm no duplicate non-null tuples before merge/apply.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_content_events_identity
ON user_content_events(item_id, event_type, render_id)
WHERE render_id IS NOT NULL;
