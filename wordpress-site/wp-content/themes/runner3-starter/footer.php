</main>
<footer class="site-footer">
  <div class="wrap">
    <div class="footer-top">
      <div class="footer-mark">OFFSET.</div>
      <div class="footer-col">
        <div class="kicker">Explore</div><br>
        <a href="<?php echo esc_url(home_url('/#latest')); ?>">Latest</a>
        <?php foreach (get_categories(['number' => 4, 'orderby' => 'count', 'order' => 'DESC']) as $cat): ?>
          <a href="<?php echo esc_url(get_category_link($cat)); ?>"><?php echo esc_html($cat->name); ?></a>
        <?php endforeach; ?>
      </div>
      <div class="footer-col">
        <div class="kicker">Journal</div><br>
        <?php if ($about = get_page_by_path('about')): ?><a href="<?php echo esc_url(get_permalink($about)); ?>">About</a><?php endif; ?>
        <?php if ($contact = get_page_by_path('contact')): ?><a href="<?php echo esc_url(get_permalink($contact)); ?>">Contact</a><?php endif; ?>
        <a href="<?php echo esc_url(get_feed_link()); ?>">RSS</a>
      </div>
    </div>
    <div class="footer-bottom"><span>Independent editorial journal</span><span>© <?php echo esc_html(date('Y')); ?> OFFSET</span></div>
  </div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
