FROM wordpress:php8.3-apache

# Runner3 owns the reproducible WordPress code layer. Runtime content stays in TiDB;
# files changed from wp-admin are ephemeral on Render Free and should be committed here.
COPY wp-content/themes/runner3-starter /usr/src/wordpress/wp-content/themes/runner3-starter
COPY wp-content/mu-plugins /usr/src/wordpress/wp-content/mu-plugins
COPY render-entrypoint.sh /usr/local/bin/render-entrypoint.sh

RUN chmod +x /usr/local/bin/render-entrypoint.sh

ENTRYPOINT ["render-entrypoint.sh"]
CMD ["apache2-foreground"]
