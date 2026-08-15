# Security Policy

## Scope

`runner-3` is intentionally public and is restricted to public-source web crawling and public/derived processing.

Do not use this repository to crawl pages that require login, cookies, authenticated sessions, private links, or account access.

## Secrets

Never commit or place in `jobs/*.json`:

- Dropbox access or refresh tokens;
- Google service-account JSON or private keys;
- OAuth client secrets;
- API keys;
- cookies or session identifiers;
- passwords;
- `.env`, `credentials.json`, or `token.json` contents.

If a destination integration needs credentials, inject them through GitHub Actions Secrets at runtime. Do not echo them, transform them into logs, or include them in artifacts.

## Artifact policy

Generic crawl artifacts are opt-in:

- `artifact_policy: none` — no artifact upload;
- `artifact_policy: text` — public extracted text + safe metadata;
- `artifact_policy: raw` — public raw HTML + text + safe metadata.

Any artifact-producing job must declare `source_visibility: public`.

Response headers are not persisted by the crawler.

Private/sensitive outputs must be sent to private storage by a dedicated workflow and removed locally; they must not be uploaded as GitHub Actions artifacts in this public repository.

## Workflow safety

- Keep `permissions: contents: read` unless a narrowly scoped job demonstrably needs more.
- Do not add `pull_request_target` workflows that execute contributor-controlled code.
- Do not persist GitHub credentials during checkout when write access is unnecessary.
- Review third-party Actions before use.

## Incident response

If a credential is ever committed or exposed in a workflow log/artifact, revoke/rotate the credential first. Removing the file from the latest branch does not remove it from Git history.
