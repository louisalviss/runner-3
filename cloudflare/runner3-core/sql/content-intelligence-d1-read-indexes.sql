-- Content Intelligence D1: targeted read-quota fix, 2026-11-12.
-- Apply ONLY to runner3-content-intelligence using explicit --remote --file.
-- No table rebuild, data rewrite, deletion, or new database.
-- One-time index creation is an intentional, bounded D1 write operation.
CREATE INDEX IF NOT EXISTS idx_content_items_collector_item
  ON content_items(json_extract(metadata_json,'$.collector'), item_id);
CREATE INDEX IF NOT EXISTS idx_user_content_events_item_type
  ON user_content_events(item_id, event_type);
