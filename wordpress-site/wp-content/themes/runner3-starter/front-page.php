<?php
get_header();
$latest = get_posts(['numberposts' => 7, 'post_status' => 'publish']);
$featured = $latest[0] ?? null;
$stories = array_slice($latest, 1);
$categories = get_categories(['number' => 4, 'orderby' => 'count', 'order' => 'DESC']);
?>

<section class="signal-stage">
  <div class="wrap signal-stage__inner">
    <div class="signal-stage__meta kicker">
      <span>OFFSET / FIELD SIGNAL 001</span>
      <span>Technology · culture · systems</span>
    </div>

    <h1 class="signal-title" aria-label="See what moves underneath">
      <span>See</span>
      <span>what moves</span>
      <span class="signal-title__serif">underneath.</span>
    </h1>

    <?php if ($featured): ?>
      <a class="signal-orbit" href="<?php echo esc_url(get_permalink($featured)); ?>" aria-label="Read <?php echo esc_attr(get_the_title($featured)); ?>">
        <span class="signal-orbit__ring" aria-hidden="true"></span>
        <span class="signal-orbit__image"><img src="<?php echo esc_url(runner3_story_image($featured->ID)); ?>" alt="" loading="eager"></span>
        <span class="signal-orbit__badge"><b>00</b><em>FEATURE</em></span>
      </a>
      <div class="signal-stage__feature">
        <span><?php echo esc_html(get_the_category($featured->ID)[0]->name ?? 'Feature'); ?> / <?php echo esc_html(runner3_read_time($featured->ID)); ?> MIN</span>
        <strong><?php echo esc_html(get_the_title($featured)); ?></strong>
      </div>
    <?php endif; ?>

    <div class="signal-stage__foot">
      <p>Independent notes for people who would rather understand the mechanism than watch the feed.</p>
      <a href="#latest">Scroll to tune ↓</a>
    </div>
  </div>
</section>

<?php if ($featured): $featured_cat = get_the_category($featured->ID)[0] ?? null; ?>
<section class="feature-scene" id="latest">
  <div class="wrap feature-scene__grid" data-reveal>
    <div class="scene-index">00</div>
    <div class="scene-copy">
      <div class="kicker">Lead signal / <?php echo esc_html($featured_cat ? $featured_cat->name : 'Journal'); ?></div>
      <h2><a href="<?php echo esc_url(get_permalink($featured)); ?>"><?php echo esc_html(get_the_title($featured)); ?></a></h2>
      <p><?php echo esc_html(wp_trim_words(get_the_excerpt($featured), 38)); ?></p>
      <a class="scene-link" href="<?php echo esc_url(get_permalink($featured)); ?>">Enter the story ↗</a>
    </div>
    <a class="scene-image" href="<?php echo esc_url(get_permalink($featured)); ?>"><img src="<?php echo esc_url(runner3_story_image($featured->ID)); ?>" alt="" loading="lazy"></a>
    <div class="scene-caption kicker">Observed / <?php echo esc_html(get_the_date('M Y', $featured)); ?></div>
  </div>
</section>
<?php endif; ?>

<section class="reel">
  <div class="wrap reel-head" data-reveal>
    <div class="kicker">01—06 / Current transmissions</div>
    <h2>Six things<br><em>worth noticing.</em></h2>
  </div>

  <div class="wrap reel-list">
    <?php foreach ($stories as $i => $post): $cat = get_the_category($post->ID)[0] ?? null; $n = $i + 1; ?>
      <article class="reel-story <?php echo $i % 2 ? 'reel-story--reverse' : ''; ?>" data-reveal>
        <div class="reel-number">0<?php echo esc_html($n); ?></div>
        <a class="reel-image" href="<?php echo esc_url(get_permalink($post)); ?>"><img src="<?php echo esc_url(runner3_story_image($post->ID)); ?>" alt="" loading="lazy"></a>
        <div class="reel-copy">
          <div class="reel-meta kicker"><span><?php echo esc_html($cat ? $cat->name : 'Journal'); ?></span><span><?php echo esc_html(runner3_read_time($post->ID)); ?> min</span></div>
          <h3><a href="<?php echo esc_url(get_permalink($post)); ?>"><?php echo esc_html(get_the_title($post)); ?></a></h3>
          <p><?php echo esc_html(wp_trim_words(get_the_excerpt($post), 24)); ?></p>
          <a class="reel-link" href="<?php echo esc_url(get_permalink($post)); ?>">Read signal ↗</a>
        </div>
      </article>
    <?php endforeach; ?>
  </div>
</section>

<section class="interrupt">
  <div class="wrap interrupt-inner" data-reveal>
    <div class="kicker">A working position</div>
    <p>Most feeds reward <span>reaction.</span><br>We are interested in <em>structure.</em></p>
  </div>
</section>

<section class="territories">
  <div class="wrap territories-head" data-reveal>
    <div class="kicker">Index / Territories</div>
    <h2>Choose a lens.</h2>
  </div>
  <div class="territory-list">
    <?php if ($categories): foreach ($categories as $i => $category): ?>
      <a class="territory" href="<?php echo esc_url(get_category_link($category)); ?>" data-reveal>
        <span class="territory-num">0<?php echo esc_html($i + 1); ?></span>
        <strong><?php echo esc_html($category->name); ?></strong>
        <span><?php echo esc_html($category->count); ?> stories ↗</span>
      </a>
    <?php endforeach; endif; ?>
  </div>
</section>

<section class="signal-close">
  <div class="wrap signal-close__grid" data-reveal>
    <div class="kicker">No algorithm required.</div>
    <h2>Stay<br><em>offset.</em></h2>
    <div class="signal-close__copy">
      <p>One compact dispatch when there is something worth sending. No daily noise.</p>
      <form class="signal-form" onsubmit="return false"><input type="email" placeholder="you@example.com" aria-label="Email"><button type="submit">JOIN ↗</button></form>
    </div>
  </div>
</section>

<?php get_footer(); ?>
