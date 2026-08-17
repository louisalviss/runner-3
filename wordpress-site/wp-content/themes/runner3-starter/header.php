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
