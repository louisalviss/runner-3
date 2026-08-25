INSERT INTO sites (
  site_id, name, public_url, origin_url, status, current_deployment, metadata_json, updated_at
) VALUES
  (
    'site1',
    'Site 1',
    'https://runner3wp.pntr.dev/',
    'https://runner3-factory-smoke-2.wasmer.app/',
    'canonical',
    '7993caf180d91f33720ed3d0d06c387fcea425d1',
    '{"proof":"q58-320px","hero_bytes":9676,"production_run":"32780532371","baseline_job":"97600652870"}',
    CURRENT_TIMESTAMP
  ),
  (
    'site2',
    'Site 2',
    'https://runner3-wp-a94b8fd2.wasmer.app/',
    'https://runner3-wp-a94b8fd2.wasmer.app/',
    'next',
    NULL,
    '{"role":"generic-engine-proof-of-reuse"}',
    CURRENT_TIMESTAMP
  ),
  (
    'site3',
    'Site 3',
    'https://runner3-speed-site3-realistic.wasmer.app/',
    'https://runner3-speed-site3-realistic.wasmer.app/',
    'pending',
    NULL,
    '{"role":"third-site-validation"}',
    CURRENT_TIMESTAMP
  )
ON CONFLICT(site_id) DO UPDATE SET
  name = excluded.name,
  public_url = excluded.public_url,
  origin_url = excluded.origin_url,
  status = excluded.status,
  current_deployment = COALESCE(excluded.current_deployment, sites.current_deployment),
  metadata_json = excluded.metadata_json,
  updated_at = CURRENT_TIMESTAMP;
