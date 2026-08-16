<?php get_header(); ?>
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <div class="eyebrow">WordPress / Runner3</div>
      <h1><?php bloginfo('name'); ?></h1>
      <p class="lead"><?php echo esc_html(get_bloginfo('description') ?: 'A fast, clean WordPress site built and deployed automatically with Runner3.'); ?></p>
      <a class="button" href="#features">Explore</a>
    </div>
    <div class="card">
      <strong>Ready to edit</strong>
      <p>Theme, core pages and deployment pipeline are already wired. Replace this starter copy with the real site content when the brief is defined.</p>
    </div>
  </div>
</section>

<section class="section" id="features">
  <div class="wrap">
    <h2>Built as a practical starter</h2>
    <div class="grid-3">
      <div class="card"><strong>Fast</strong><p>Minimal theme with no page-builder dependency.</p></div>
      <div class="card"><strong>Responsive</strong><p>Works on mobile and desktop out of the box.</p></div>
      <div class="card"><strong>Deployable</strong><p>Runner3 can package and publish changes over FTP.</p></div>
    </div>
  </div>
</section>
<?php get_footer(); ?>
