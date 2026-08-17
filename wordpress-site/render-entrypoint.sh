#!/bin/sh
set -eu

# Render routes public traffic to the port in $PORT.
PORT="${PORT:-10000}"
sed -ri "s/^Listen [0-9]+/Listen ${PORT}/" /etc/apache2/ports.conf
sed -ri "s/<VirtualHost \*:[0-9]+>/<VirtualHost *:${PORT}>/" /etc/apache2/sites-available/000-default.conf

# Accept the same variables used by PingCAP's WordPress + TiDB guide.
if [ -n "${TIDB_HOST:-}" ]; then
  export WORDPRESS_DB_HOST="${TIDB_HOST}:${TIDB_PORT:-4000}"
fi
[ -n "${TIDB_USER:-}" ] && export WORDPRESS_DB_USER="${TIDB_USER}"
[ -n "${TIDB_PASSWORD:-}" ] && export WORDPRESS_DB_PASSWORD="${TIDB_PASSWORD}"
export WORDPRESS_DB_NAME="${TIDB_DB_NAME:-test}"
export WORDPRESS_DB_COLLATE="utf8mb4_bin"

# TiDB Starter requires TLS. Also make WordPress HTTPS-aware behind Render's proxy.
if [ -z "${WORDPRESS_CONFIG_EXTRA:-}" ]; then
  WORDPRESS_CONFIG_EXTRA="$(cat <<'PHP'
define('MYSQL_CLIENT_FLAGS', MYSQLI_CLIENT_SSL);
define('MYSQL_SSL_CA', '/etc/ssl/certs/ca-certificates.crt');
define('DB_COLLATE', 'utf8mb4_bin');
if (!empty(\$_SERVER['HTTP_X_FORWARDED_PROTO']) && \$_SERVER['HTTP_X_FORWARDED_PROTO'] === 'https') {
    \$_SERVER['HTTPS'] = 'on';
}
PHP
)"
  export WORDPRESS_CONFIG_EXTRA
fi

exec docker-entrypoint.sh "$@"
