<?php
get_header();
$latest = get_posts(['numberposts' => 7, 'post_status' => 'publish']);
$featured = $latest[0] ?? null;
$stories = array_slice($latest, 1);
$categories = get_categories(['number' => 4, 'orderby' => 'count', 'order' => 'DESC']);
?>
<section class="edition-hero">
  <div class="wrap">
    <div class="hero-meta kicker"><span>Vol. 01 / Digital culture & systems</span><span>Nha Trang → Everywhere</span></div>
    <h1 class="hero-title">Ideas for a world <em>moving fast.</em></h1>
    <?php if ($featured): ?>
      <article class="hero-feature">
        <div class="hero-copy">
          <div class="kicker"><?php echo esc_html(get_the_category($featured->ID)[0]->name ?? 'Feature'); ?> / <?php echo esc_html(runner3_read_time($featured->ID)); ?> min read</div>
          <h2><a href="<?php echo esc_url(get_permalink($featured)); ?>"><?php echo esc_html(get_the_title($featured)); ?></a></h2>
          <div class="hero-excerpt"><?php echo esc_html(wp_trim_words(get_the_excerpt($featured), 34)); ?></div>
        </div>
        <a class="hero-image" href="<?php echo esc_url(get_permalink($featured)); ?>" aria-label="Read <?php echo esc_attr(get_the_title($featured)); ?>">
          <img src="<?php echo esc_url(runner3_story_image($featured->ID)); ?>" alt="" loading="eager">
        </a>
      </article>
    <?php else: ?>
      <article class="hero-feature"><div class="hero-copy"><div class="kicker">Ready</div><h2>Publish the first story.</h2><p class="hero-excerpt">This editorial system is ready for real content.</p></div></article>
    <?php endif; ?>
  </div>
</section>

<section class="section" id="latest">
  <div class="wrap">
    <div class="section-head"><div class="kicker">01 / Latest</div><h2>Signals worth keeping.</h2></div>
    <div class="story-grid">
      <?php foreach ($stories as $i => $post): $cat = get_the_category($post->ID)[0] ?? null; ?>
        <article class="story-card">
          <a class="story-image" href="<?php echo esc_url(get_permalink($post)); ?>"><img src="<?php echo esc_url(runner3_story_image($post->ID)); ?>" alt="" loading="lazy"></a>
          <div class="story-meta"><span><?php echo esc_html($cat ? $cat->name : 'Journal'); ?></span><span><?php echo esc_html(runner3_read_time($post->ID)); ?> min</span></div>
          <h3><a href="<?php echo esc_url(get_permalink($post)); ?>"><?php echo esc_html(get_the_title($post)); ?></a></h3>
          <p><?php echo esc_html(wp_trim_words(get_the_excerpt($post), 20)); ?></p>
        </article>
      <?php endforeach; ?>
    </div>
  </div>
</section>

<section class="manifesto">
  <div class="wrap manifesto-grid">
    <div class="kicker">02 / Position</div>
    <p>Less noise. Better questions. Practical ideas about <em>technology, culture and the systems underneath.</em></p>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <div class="section-head"><div class="kicker">03 / Index</div><h2>Browse by territory.</h2></div>
    <div class="category-strip">
      <?php if ($categories): foreach ($categories as $i => $category): ?>
        <a class="category-link" href="<?php echo esc_url(get_category_link($category)); ?>"><span>0<?php echo esc_html($i + 1); ?> / <?php echo esc_html($category->count); ?> stories</span><strong><?php echo esc_html($category->name); ?></strong></a>
      <?php endforeach; else: ?>
        <a class="category-link" href="#"><span>01</span><strong>Technology</strong></a>
        <a class="category-link" href="#"><span>02</span><strong>Culture</strong></a>
        <a class="category-link" href="#"><span>03</span><strong>Systems</strong></a>
        <a class="category-link" href="#"><span>04</span><strong>Field Notes</strong></a>
      <?php endif; ?>
    </div>
  </div>
</section>

<section class="newsletter">
  <div class="wrap newsletter-box">
    <h2>Stay <em>offset.</em></h2>
    <div class="newsletter-copy"><div class="kicker">A quiet inbox, occasionally.</div><p>One compact dispatch when there is something worth sending. No feed optimization, no daily noise.</p><form class="fake-form" onsubmit="return false"><input type="email" placeholder="you@example.com" aria-label="Email"><button type="submit">JOIN →</button></form></div>
  </div>
</section>
<?php get_footer(); ?>
