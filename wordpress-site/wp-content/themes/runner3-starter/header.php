<?php
// Finalize anonymous public HTML into one response body so Wasmer CDN can store it
// with a concrete Content-Length. Admin/login/REST/feed do not render this template.
if (function_exists('runner3_public_edge_cache_eligible') && runner3_public_edge_cache_eligible()) {
    @ini_set('zlib.output_compression', '0');
    header('X-Edge-Origin-Stamp: ' . sprintf('%.6f', microtime(true)), true);
    ob_start(static function ($html) {
        if (!headers_sent()) {
            header_remove('Transfer-Encoding');
            header('Content-Length: ' . strlen($html), true);
        }
        return $html;
    });
}
?>
<!doctype html>
<html <?php language_attributes(); ?>>
<head>
  <meta charset="<?php bloginfo('charset'); ?>">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<header class="site-header">
  <div class="wrap header-row">
    <a class="brand" href="<?php echo esc_url(home_url('/')); ?>">OFFSET<span class="brand-dot"></span></a>
    <nav class="nav" aria-label="Primary navigation">
      <?php wp_nav_menu([
          'theme_location' => 'primary',
          'container' => false,
          'fallback_cb' => 'runner3_primary_fallback',
          'depth' => 1,
      ]); ?>
    </nav>
    <div class="header-meta">Independent journal / <?php echo esc_html(date('Y')); ?></div>
  </div>
</header>
<main>
