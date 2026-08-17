<?php get_header(); ?>
<?php while (have_posts()) : the_post(); ?>
  <article class="article-shell">
    <header class="article-head">
      <div class="kicker">Page / OFFSET</div>
      <h1 class="page-title"><?php the_title(); ?></h1>
    </header>
    <div class="article-body"><?php the_content(); ?></div>
  </article>
<?php endwhile; ?>
<?php get_footer(); ?>
