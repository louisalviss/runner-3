<?php get_header(); ?>
<?php while (have_posts()) : the_post(); $cat = get_the_category()[0] ?? null; ?>
  <article class="article-shell">
    <header class="article-head">
      <div>
        <div class="kicker"><?php echo esc_html($cat ? $cat->name : 'Journal'); ?></div>
        <div class="story-meta" style="margin-top:14px;display:block"><?php echo esc_html(get_the_date('M j, Y')); ?> · <?php echo esc_html(runner3_read_time()); ?> min read</div>
      </div>
      <h1 class="article-title"><?php the_title(); ?></h1>
    </header>
    <div class="article-hero"><img src="<?php echo esc_url(runner3_story_image(get_the_ID())); ?>" alt="" loading="eager"></div>
    <div class="article-body"><?php the_content(); ?></div>
  </article>
<?php endwhile; ?>
<?php get_footer(); ?>
