-- Idempotency guard for retryable Content Intelligence event delivery.
-- Same item + event type + non-null render_id is applied once.

DELETE FROM user_content_events
WHERE render_id IS NOT NULL
  AND id NOT IN (
    SELECT MIN(id)
    FROM user_content_events
    WHERE render_id IS NOT NULL
    GROUP BY item_id, event_type, render_id
  );

CREATE TRIGGER IF NOT EXISTS trg_user_content_events_render_dedupe
BEFORE INSERT ON user_content_events
WHEN NEW.render_id IS NOT NULL
 AND EXISTS (
   SELECT 1 FROM user_content_events
   WHERE item_id = NEW.item_id
     AND event_type = NEW.event_type
     AND render_id = NEW.render_id
 )
BEGIN
  SELECT RAISE(IGNORE);
END;
