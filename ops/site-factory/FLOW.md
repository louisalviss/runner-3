# Runner3 Site Factory — canonical flow

Goal: one request creates one WordPress site on the existing Wasmer account and one PNTR subdomain on the existing GitHub-bound PNTR account.

## Trigger

The assistant should create or replace `ops/site-factory/request.json` with a new unique `requestId`.

Example:

```json
{
  "requestId": "site-20260817-001",
  "subdomain": "my-site",
  "siteTitle": "My Site",
  "strictName": false
}
```

A push that changes only that request file triggers `.github/workflows/site-factory.yml`.

## Canonical sequence

1. Restore the encrypted existing Wasmer account/session.
2. Restore the encrypted PNTR account token.
3. Check PNTR quota/name availability and prevent duplicate managed sites.
4. Create a WordPress Starter app inside the existing Wasmer account.
5. Initialize WordPress when required; generate admin credentials only when the installer is present.
6. Add the new PNTR hostname to the Wasmer app and capture Wasmer's CNAME target.
7. Create the PNTR subdomain through the authenticated PNTR REST API.
8. Add the CNAME record in PNTR.
9. Verify HTTPS on the PNTR hostname.
10. Persist safe inventory/status and encrypt per-site credentials.

## State and secrets

- Safe inventory: `ops/site-factory/sites.json`
- Last safe result: `ops/site-factory/last-run.json`
- Per-site sensitive state: `ops/site-factory/secrets/<domain>.aes`
- Existing Wasmer account state: `ops/wasmer/state.automation.aes`
- Existing Wasmer browser session: `ops/wasmer/browser-state.aes`
- PNTR account token: `ops/pntr/account-token.aes`

Sensitive files use AES-256-CBC + PBKDF2 (200000 iterations) with the existing Runner3 automation key. Raw account tokens/passwords must never be committed or printed.

## Rules

- Reuse the current Wasmer account. Do not use the legacy `wasmer-provision.mjs` path that creates a new Wasmer account per run.
- Reuse the GitHub-bound PNTR account. Do not restore or recreate anonymous/guest PNTR sessions.
- Intended free inventory ceiling is three PNTR subdomains; the factory performs an account-side quota check before creating anything.
- If a requested PNTR name is unavailable and `strictName=false`, suffix variants are tried automatically.
- Do not create a new request merely to test the factory. Use safe status/preflight checks instead.

## User-facing shorthand

When the user says `tạo site mới`, `tạo site <name>`, or equivalent, the normal action is: write one new `request.json`, let the factory run, then report the resulting PNTR URL and status. No PNTR login, VNC, guest-cookie bridge, or new Wasmer signup should be required during a normal run.
