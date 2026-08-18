# WordPress Restore

Production restore flow for disposable WordPress staging sites created by the WordPress Site Factory.

## What this flow does

1. Opens the existing Wasmer staging app from `ops/site-factory/<site_slug>.json`.
2. Enters WordPress Admin through the Wasmer control plane.
3. Obtains a WordPress REST nonce and ensures All-in-One WP Migration is active.
4. Gets a `.wpress` backup from either an existing server backup or an external URL.
5. Verifies the backup SHA-256 when supplied.
6. Creates an AI1WM import job.
7. Uploads the archive using the required multipart field `upload_file` with `auto_confirm=true`.
8. Polls the import job and public WordPress state until completion or the configured watch window expires.
9. Persists a safe status file under `ops/wordpress-restore/<request_id>.json`.

The flow intentionally does **not** call `/ai1wm/v1/backups/<name>/restore`: AI1WM Free returns `403 upgrade_required` for that route. The tested free path is download -> `/imports` -> multipart upload -> import.

## Safety boundary

Restores are restricted to `*.wasmer.app` disposable staging targets. Treat every client backup as untrusted PHP and database content. Do not restore arbitrary backups into infrastructure that also contains unrelated production credentials.

The current encrypted Wasmer account state is `ops/wasmer/state.automation.aes`. Prefer a dedicated `WASMER_AUTOMATION_KEY` GitHub secret. The workflow temporarily falls back to the legacy `CLOUDFLARE_API_TOKEN` key only to preserve compatibility while secrets are migrated.

This repository is public. Do not commit credential-bearing or long-lived signed backup URLs into `restore/requests/`. For sensitive external backups, use `workflow_dispatch` with a short-lived URL or move the restore runner to a private repository.

## Request schema

Create one JSON request per restore under `restore/requests/`, or pass its path through `workflow_dispatch`.

```json
{
  "request_id": "restore-20260818-example",
  "site_slug": "runner5-restore-lab-1",
  "backup": {
    "source": "server",
    "name": "example.wpress",
    "sha256": "optional-lowercase-sha256"
  },
  "verify": {
    "title": "Expected Site Title",
    "post_slug": "optional-marker-post",
    "page_slug": "optional-marker-page"
  },
  "watch_minutes": 75
}
```

For an external archive:

```json
{
  "request_id": "restore-20260818-external",
  "site_slug": "staging-site-slug",
  "backup": {
    "source": "url",
    "url": "https://short-lived.example/backup.wpress",
    "sha256": "recommended-sha256"
  },
  "verify": {
    "title": "Expected Restored Title"
  }
}
```

To resume a long import without uploading again, add:

```json
{
  "resume_import_job_id": "6a840ab96b5af"
}
```

Normally a rerun of the same request automatically reads the prior job id from `ops/wordpress-restore/<request_id>.json`.

## Statuses

- `RESTORE_VERIFIED`: import completed and all supplied verification markers matched.
- `RESTORE_COMPLETE`: import reported success and WordPress is reachable; no markers were supplied.
- `RESTORE_COMPLETE_UNVERIFIED_MARKERS`: import reported success but supplied markers did not match; inspect before promoting.
- `RESTORE_IN_PROGRESS`: import is still running when the watch window closes. Rerun the same request to resume watching without re-uploading.
- `FAILED`: authentication, backup validation, plugin setup, upload, import, or explicit import failure.

## Validated proof

On 2026-08-18 the restore lab proved the full chain on `runner5-restore-lab-1`:

- `.wpress` backup: 65,754,860 bytes.
- SHA-256: `908727acbcf24d27e8fd31db59c27e862cfded3dcc2f171091d07c9ad113b403`.
- Controlled mutation changed the site title and removed a known post and page.
- AI1WM Free direct backup restore returned `403 upgrade_required`.
- AI1WM REST import accepted the archive with HTTP `202` and restored 1,296 files.
- Final status: `RESTORE_VERIFIED`; the original title, marker post, and marker page all returned.

After restore verification, continue to the separate WordPress Site Optimization flow only when explicitly requested.
