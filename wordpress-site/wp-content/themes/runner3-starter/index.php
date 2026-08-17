<?php get_header(); ?>
<section class="archive-hero">
  <div class="wrap">
    <div class="kicker"><?php echo is_archive() ? 'Archive / Index' : 'Journal / All stories'; ?></div>
    <h1><?php echo is_archive() ? wp_kses_post(get_the_archive_title()) : 'The Journal'; ?></h1>
    <?php if (is_archive() && get_the_archive_description()): ?><div class="hero-excerpt"><?php echo wp_kses_post(get_the_archive_description()); ?></div><?php endif; ?>
  </div>
</section>
<section class="section">
  <div class="wrap archive-grid">
    <?php if (have_posts()) : while (have_posts()) : the_post(); $cat = get_the_category()[0] ?? null; ?>
      <article class="story-card">
        <a class="story-image" href="<?php the_permalink(); ?>"><img src="<?php echo esc_url(runner3_story_image(get_the_ID())); ?>" alt="" loading="lazy"></a>
        <div class="story-meta"><span><?php echo esc_html($cat ? $cat->name : 'Journal'); ?></span><span><?php echo esc_html(runner3_read_time()); ?> min</span></div>
        <h3><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h3>
        <p><?php echo esc_html(wp_trim_words(get_the_excerpt(), 22)); ?></p>
      </article>
    <?php endwhile; else: ?>
      <p>No stories yet.</p>
    <?php endif; ?>
  </div>
</section>
<?php get_footer(); ?>
