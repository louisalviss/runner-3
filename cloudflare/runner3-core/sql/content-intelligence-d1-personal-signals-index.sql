-- Content Intelligence D1, 2026-11-12: index only explicit preference events.
-- Apply to runner3-content-intelligence, never runner3-core.
-- Same predicate as ITEM_SIGNAL_CTE; includes event_at and groups by item_id.
CREATE INDEX IF NOT EXISTS idx_user_content_events_preference_signal
  ON user_content_events(item_id, event_type, event_at)
  WHERE event_type <> 'shown';
