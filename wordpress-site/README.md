# Runner3 WordPress Site

This directory contains a minimal WordPress starter theme and a must-use bootstrap plugin. The GitHub Actions workflow is `.github/workflows/wordpress-site.yml`.

## Build

Run **WordPress Site Factory** from GitHub Actions with `deploy=false`. The workflow downloads the latest WordPress release, adds the Runner3 starter content, validates PHP syntax, and uploads a 3-day build artifact.

## InfinityFree first deployment

Create a free InfinityFree hosting account and subdomain. In the hosting client area, note the FTP username/password. The default FTP host is `ftpupload.net` and the normal web root is `/htdocs/`.

Add these GitHub Actions repository secrets:

- `WP_FTP_USERNAME` — InfinityFree FTP username.
- `WP_FTP_PASSWORD` — InfinityFree hosting/FTP password.
- `WP_FTP_HOST` — optional; omit to use `ftpupload.net`.
- `WP_FTP_DIR` — optional; omit to use `/htdocs/`.

Never commit FTP or database credentials to this public repository.

For a new empty hosting account, run the workflow with `deploy=true` and `deploy_scope=full`. After WordPress is installed, normal updates should use `deploy_scope=content` to avoid repeatedly uploading WordPress core.

## Database setup

InfinityFree databases are created from the hosting control panel. Keep database credentials out of GitHub. Complete WordPress database configuration through the hosting/WordPress installer or place them in server-side `wp-config.php`; the deployment workflow deliberately excludes `wp-config.php`.

## Automatic site bootstrap

Once WordPress can connect to its database, `runner3-bootstrap.php` automatically:

- activates the `runner3-starter` theme;
- creates Home, About and Contact pages if missing;
- configures Home as the static front page;
- marks the bootstrap as complete so it only runs once.
