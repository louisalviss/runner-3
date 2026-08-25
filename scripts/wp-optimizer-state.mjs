#!/usr/bin/env node

import fs from 'node:fs';
import { spawnSync } from 'node:child_process';

const WRANGLER_VERSION = process.env.WP_OPTIMIZER_WRANGLER_VERSION || '4.124.0';
const DEFAULT_DATABASE = process.env.WP_OPTIMIZER_D1_DB || 'runner3-wp-optimizer';

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

function sqlValue(value) {
  if (value === undefined || value === null) return 'NULL';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'NULL';
    return String(value);
  }
  if (typeof value === 'boolean') return value ? '1' : '0';
  return `'${String(value).replaceAll("'", "''")}'`;
}

function jsonValue(value, fallback = {}) {
  return sqlValue(JSON.stringify(value ?? fallback));
}

function required(event, key) {
  const value = event[key];
  if (value === undefined || value === null || value === '') {
    throw new Error(`missing required event field: ${key}`);
  }
  return value;
}

function buildSql(event) {
  const type = required(event, 'type');

  if (type === 'site.upsert') {
    return `
INSERT INTO sites (
  site_id, name, public_url, origin_url, status, current_deployment, metadata_json, updated_at
) VALUES (
  ${sqlValue(required(event, 'site_id'))},
  ${sqlValue(required(event, 'name'))},
  ${sqlValue(required(event, 'public_url'))},
  ${sqlValue(event.origin_url)},
  ${sqlValue(event.status || 'active')},
  ${sqlValue(event.current_deployment)},
  ${jsonValue(event.metadata)},
  CURRENT_TIMESTAMP
)
ON CONFLICT(site_id) DO UPDATE SET
  name = excluded.name,
  public_url = excluded.public_url,
  origin_url = excluded.origin_url,
  status = excluded.status,
  current_deployment = COALESCE(excluded.current_deployment, sites.current_deployment),
  metadata_json = excluded.metadata_json,
  updated_at = CURRENT_TIMESTAMP;`;
  }

  if (type === 'candidate.upsert') {
    return `
INSERT INTO candidates (
  candidate_id, site_id, kind, parameters_json, commit_sha, artifact_prefix, status, updated_at
) VALUES (
  ${sqlValue(required(event, 'candidate_id'))},
  ${sqlValue(required(event, 'site_id'))},
  ${sqlValue(required(event, 'kind'))},
  ${jsonValue(event.parameters)},
  ${sqlValue(event.commit_sha)},
  ${sqlValue(event.artifact_prefix)},
  ${sqlValue(event.status || 'proposed')},
  CURRENT_TIMESTAMP
)
ON CONFLICT(candidate_id) DO UPDATE SET
  kind = excluded.kind,
  parameters_json = excluded.parameters_json,
  commit_sha = excluded.commit_sha,
  artifact_prefix = excluded.artifact_prefix,
  status = excluded.status,
  updated_at = CURRENT_TIMESTAMP;`;
  }

  if (type === 'run.start') {
    return `
INSERT INTO optimization_runs (
  run_id, site_id, phase, baseline_run_id, candidate_id, workflow_name,
  workflow_run_id, workflow_job_id, status, verdict, commit_sha, started_at, metadata_json
) VALUES (
  ${sqlValue(required(event, 'run_id'))},
  ${sqlValue(required(event, 'site_id'))},
  ${sqlValue(required(event, 'phase'))},
  ${sqlValue(event.baseline_run_id)},
  ${sqlValue(event.candidate_id)},
  ${sqlValue(event.workflow_name)},
  ${sqlValue(event.workflow_run_id)},
  ${sqlValue(event.workflow_job_id)},
  ${sqlValue(event.status || 'running')},
  ${sqlValue(event.verdict)},
  ${sqlValue(event.commit_sha)},
  COALESCE(${sqlValue(event.started_at)}, CURRENT_TIMESTAMP),
  ${jsonValue(event.metadata)}
)
ON CONFLICT(run_id) DO UPDATE SET
  status = excluded.status,
  workflow_job_id = COALESCE(excluded.workflow_job_id, optimization_runs.workflow_job_id),
  commit_sha = COALESCE(excluded.commit_sha, optimization_runs.commit_sha),
  metadata_json = excluded.metadata_json;`;
  }

  if (type === 'run.finish') {
    return `
UPDATE optimization_runs SET
  status = ${sqlValue(event.status || 'completed')},
  verdict = ${sqlValue(event.verdict)},
  workflow_job_id = COALESCE(${sqlValue(event.workflow_job_id)}, workflow_job_id),
  finished_at = COALESCE(${sqlValue(event.finished_at)}, CURRENT_TIMESTAMP),
  metadata_json = ${jsonValue(event.metadata)}
WHERE run_id = ${sqlValue(required(event, 'run_id'))};`;
  }

  if (type === 'measurement.upsert') {
    return `
INSERT INTO measurements (
  run_id, phase, sample_no, valid, performance, accessibility, best_practices, seo,
  fcp_ms, lcp_ms, tbt_ms, cls, collector, result_url, failure_reason,
  raw_artifact_key, measured_at, raw_json
) VALUES (
  ${sqlValue(required(event, 'run_id'))},
  ${sqlValue(required(event, 'phase'))},
  ${sqlValue(required(event, 'sample_no'))},
  ${sqlValue(event.valid !== false)},
  ${sqlValue(event.performance)},
  ${sqlValue(event.accessibility)},
  ${sqlValue(event.best_practices)},
  ${sqlValue(event.seo)},
  ${sqlValue(event.fcp_ms)},
  ${sqlValue(event.lcp_ms)},
  ${sqlValue(event.tbt_ms)},
  ${sqlValue(event.cls)},
  ${sqlValue(event.collector)},
  ${sqlValue(event.result_url)},
  ${sqlValue(event.failure_reason)},
  ${sqlValue(event.raw_artifact_key)},
  COALESCE(${sqlValue(event.measured_at)}, CURRENT_TIMESTAMP),
  ${jsonValue(event.raw)}
)
ON CONFLICT(run_id, phase, sample_no) DO UPDATE SET
  valid = excluded.valid,
  performance = excluded.performance,
  accessibility = excluded.accessibility,
  best_practices = excluded.best_practices,
  seo = excluded.seo,
  fcp_ms = excluded.fcp_ms,
  lcp_ms = excluded.lcp_ms,
  tbt_ms = excluded.tbt_ms,
  cls = excluded.cls,
  collector = excluded.collector,
  result_url = excluded.result_url,
  failure_reason = excluded.failure_reason,
  raw_artifact_key = excluded.raw_artifact_key,
  measured_at = excluded.measured_at,
  raw_json = excluded.raw_json;`;
  }

  if (type === 'gate.upsert') {
    return `
INSERT INTO gates (run_id, gate_name, status, details_json, evaluated_at)
VALUES (
  ${sqlValue(required(event, 'run_id'))},
  ${sqlValue(required(event, 'gate_name'))},
  ${sqlValue(required(event, 'status'))},
  ${jsonValue(event.details)},
  COALESCE(${sqlValue(event.evaluated_at)}, CURRENT_TIMESTAMP)
)
ON CONFLICT(run_id, gate_name) DO UPDATE SET
  status = excluded.status,
  details_json = excluded.details_json,
  evaluated_at = excluded.evaluated_at;`;
  }

  if (type === 'decision.upsert') {
    return `
INSERT INTO decisions (
  run_id, verdict, baseline_median_lcp_ms, candidate_median_lcp_ms,
  tolerance_ms, reason, decided_at, details_json
) VALUES (
  ${sqlValue(required(event, 'run_id'))},
  ${sqlValue(required(event, 'verdict'))},
  ${sqlValue(event.baseline_median_lcp_ms)},
  ${sqlValue(event.candidate_median_lcp_ms)},
  ${sqlValue(event.tolerance_ms)},
  ${sqlValue(event.reason)},
  COALESCE(${sqlValue(event.decided_at)}, CURRENT_TIMESTAMP),
  ${jsonValue(event.details)}
)
ON CONFLICT(run_id) DO UPDATE SET
  verdict = excluded.verdict,
  baseline_median_lcp_ms = excluded.baseline_median_lcp_ms,
  candidate_median_lcp_ms = excluded.candidate_median_lcp_ms,
  tolerance_ms = excluded.tolerance_ms,
  reason = excluded.reason,
  decided_at = excluded.decided_at,
  details_json = excluded.details_json;

UPDATE optimization_runs SET
  verdict = ${sqlValue(required(event, 'verdict'))},
  status = 'completed',
  finished_at = CURRENT_TIMESTAMP
WHERE run_id = ${sqlValue(required(event, 'run_id'))};`;
  }

  if (type === 'artifact.add') {
    return `
INSERT INTO artifacts (
  run_id, kind, r2_key, url, sha256, bytes, metadata_json, created_at
) VALUES (
  ${sqlValue(required(event, 'run_id'))},
  ${sqlValue(required(event, 'kind'))},
  ${sqlValue(event.r2_key)},
  ${sqlValue(event.url)},
  ${sqlValue(event.sha256)},
  ${sqlValue(event.bytes)},
  ${jsonValue(event.metadata)},
  CURRENT_TIMESTAMP
);`;
  }

  throw new Error(`unsupported event type: ${type}`);
}

function readEvent() {
  const eventFile = argValue('--event-file');
  if (eventFile) return JSON.parse(fs.readFileSync(eventFile, 'utf8'));
  const stdin = fs.readFileSync(0, 'utf8').trim();
  if (!stdin) throw new Error('provide --event-file <path> or JSON on stdin');
  return JSON.parse(stdin);
}

const event = readEvent();
const sql = buildSql(event).trim();

if (process.argv.includes('--dry-run')) {
  process.stdout.write(`${sql}\n`);
  process.exit(0);
}

const database = argValue('--database') || DEFAULT_DATABASE;
const result = spawnSync(
  'npx',
  [
    '--yes',
    `wrangler@${WRANGLER_VERSION}`,
    'd1',
    'execute',
    database,
    '--remote',
    '--yes',
    '--command',
    sql,
    '--json',
  ],
  {
    stdio: 'inherit',
    env: process.env,
  },
);

if (result.error) throw result.error;
process.exit(result.status ?? 1);
