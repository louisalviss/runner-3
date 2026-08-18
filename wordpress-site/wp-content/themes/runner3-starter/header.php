<?php
// Wasmer CDN Cache is app-wide, but storage is opt-in per response. Cache only
// anonymous public editorial pages; admin/login/REST never load this template,
// and personalized cookie requests are bypassed by Wasmer Edge automatically.
if (
    !is_user_logged_in() &&
    !is_preview() &&
    !is_search() &&
    !is_404() &&
    (is_front_page() || is_home() || is_singular() || is_archive())
) {
    header('Cache-Control: public, max-age=30, s-maxage=120, stale-while-revalidate=30, stale-if-error=600', true);
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
