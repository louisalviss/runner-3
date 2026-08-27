UPDATE vps_mailbox_jobs
SET status = 'failed',
    lease_owner = NULL,
    lease_until = NULL,
    last_error = 'legacy_nonopaque_id_retired',
    updated_at = CURRENT_TIMESTAMP
WHERE status IN ('queued', 'claimed')
  AND (
    length(request_id) <> 64
    OR request_id GLOB '*[^0-9a-f]*'
  );
