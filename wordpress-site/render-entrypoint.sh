#!/bin/sh
set -eu

# Render routes public traffic to the port in $PORT.
PORT="${PORT:-10000}"
sed -ri "s/^Listen [0-9]+/Listen ${PORT}/" /etc/apache2/ports.conf
sed -ri "s/<VirtualHost \*:[0-9]+>/<VirtualHost *:${PORT}>/" /etc/apache2/sites-available/000-default.conf

DB_MODE="tidb"

# One-click demo mode: Render injects its private PostgreSQL connection string.
# Parse it with PHP so URL-encoded credentials are handled safely.
if [ -n "${DATABASE_URL:-}" ]; then
  DB_MODE="postgres"
  eval "$(php -r '
    $u = parse_url(getenv("DATABASE_URL"));
    if (!$u || empty($u["host"]) || empty($u["user"]) || !array_key_exists("pass", $u)) { fwrite(STDERR, "Invalid DATABASE_URL\n"); exit(2); }
    $host = $u["host"] . ":" . ($u["port"] ?? 5432);
    $name = ltrim($u["path"] ?? "", "/");
    foreach (["WORDPRESS_DB_HOST"=>$host, "WORDPRESS_DB_USER"=>urldecode($u["user"]), "WORDPRESS_DB_PASSWORD"=>urldecode($u["pass"]), "WORDPRESS_DB_NAME"=>urldecode($name)] as $k=>$v) {
      echo "export ".$k."=".escapeshellarg($v)."\n";
    }
  ')"
else
  # Long-lived mode: same variables used by PingCAP's WordPress + TiDB guide.
  if [ -n "${TIDB_HOST:-}" ]; then
    export WORDPRESS_DB_HOST="${TIDB_HOST}:${TIDB_PORT:-4000}"
  fi
  [ -n "${TIDB_USER:-}" ] && export WORDPRESS_DB_USER="${TIDB_USER}"
  [ -n "${TIDB_PASSWORD:-}" ] && export WORDPRESS_DB_PASSWORD="${TIDB_PASSWORD}"
  export WORDPRESS_DB_NAME="${TIDB_DB_NAME:-test}"
  export WORDPRESS_DB_COLLATE="utf8mb4_bin"
fi

if [ "$DB_MODE" = "postgres" ]; then
  # PG4WP's db.php drop-in is baked into the image and selects pgsql by default.
  WORDPRESS_CONFIG_EXTRA="$(cat <<'PHP'
define('DB_DRIVER', 'pgsql');
if (!empty($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    $_SERVER['HTTPS'] = 'on';
}
PHP
)"
else
  # TiDB Starter requires TLS.
  WORDPRESS_CONFIG_EXTRA="$(cat <<'PHP'
define('MYSQL_CLIENT_FLAGS', MYSQLI_CLIENT_SSL);
define('MYSQL_SSL_CA', '/etc/ssl/certs/ca-certificates.crt');
define('DB_COLLATE', 'utf8mb4_bin');
if (!empty($_SERVER['HTTP_X_FORWARDED_PROTO']) && $_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    $_SERVER['HTTPS'] = 'on';
}
PHP
)"
fi
export WORDPRESS_CONFIG_EXTRA

exec docker-entrypoint.sh "$@"
