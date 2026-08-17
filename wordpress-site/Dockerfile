FROM wordpress:php8.3-apache

ARG PG4WP_COMMIT=ea843d1560a40cce42b9297323636bde59a9bc70

# One-click Render demo mode uses Render Postgres via PG4WP. The existing TiDB
# mode remains supported for the longer-lived MySQL-compatible route.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev curl ca-certificates \
    && docker-php-ext-install pgsql pdo_pgsql \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp/pg4wp \
    && curl --fail --location --retry 3 \
       "https://github.com/PostgreSQL-For-Wordpress/postgresql-for-wordpress/archive/${PG4WP_COMMIT}.tar.gz" \
       -o /tmp/pg4wp.tar.gz \
    && tar -xzf /tmp/pg4wp.tar.gz -C /tmp/pg4wp --strip-components=1 \
    && cp -a /tmp/pg4wp/pg4wp /usr/src/wordpress/wp-content/pg4wp \
    && cp /tmp/pg4wp/pg4wp/db.php /usr/src/wordpress/wp-content/db.php \
    && rm -rf /tmp/pg4wp /tmp/pg4wp.tar.gz

# Runner3 owns the reproducible WordPress code layer. Runtime file changes made
# from wp-admin are ephemeral on Render Free and should eventually be committed here.
COPY wp-content/themes/runner3-starter /usr/src/wordpress/wp-content/themes/runner3-starter
COPY wp-content/mu-plugins /usr/src/wordpress/wp-content/mu-plugins
COPY render-entrypoint.sh /usr/local/bin/render-entrypoint.sh

RUN chmod +x /usr/local/bin/render-entrypoint.sh

ENTRYPOINT ["render-entrypoint.sh"]
CMD ["apache2-foreground"]
