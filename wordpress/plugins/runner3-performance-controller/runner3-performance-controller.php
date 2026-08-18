<?php
/**
 * Plugin Name: Runner3 Performance Controller
 * Description: Safe site-wide loading policy for WordPress: native smart lazy loading, conservative LCP priority, iframe deferral, and rollback controls without client-side JavaScript.
 * Version: 1.0.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) {
    exit;
}

const RUNNER3_PERF_OPTION = 'runner3_performance_controller';
const RUNNER3_PERF_PAGE = 'runner3-performance-controller';

function runner3_perf_defaults() {
    return array(
        'enabled' => 1,
        'smart_lazy' => 1,
        'omit_threshold' => 1,
        'raw_html_fallback' => 1,
        'raw_eager_count' => 2,
        'lazy_iframes' => 1,
        'decode_async' => 1,
        'hero_priority' => 1,
    );
}

function runner3_perf_options() {
    return wp_parse_args((array) get_option(RUNNER3_PERF_OPTION, array()), runner3_perf_defaults());
}

function runner3_perf_sanitize($input) {
    $input = (array) $input;
    $out = runner3_perf_defaults();
    foreach (array('enabled', 'smart_lazy', 'raw_html_fallback', 'lazy_iframes', 'decode_async', 'hero_priority') as $key) {
        $out[$key] = empty($input[$key]) ? 0 : 1;
    }
    $out['omit_threshold'] = min(6, max(1, absint(isset($input['omit_threshold']) ? $input['omit_threshold'] : 1)));
    $out['raw_eager_count'] = min(6, max(1, absint(isset($input['raw_eager_count']) ? $input['raw_eager_count'] : 2)));
    return $out;
}

function runner3_perf_register_settings() {
    register_setting('runner3_perf_group', RUNNER3_PERF_OPTION, array('sanitize_callback' => 'runner3_perf_sanitize'));
}
add_action('admin_init', 'runner3_perf_register_settings');

function runner3_perf_admin_menu() {
    add_options_page('Runner3 Performance Controller', 'Runner3 Performance', 'manage_options', RUNNER3_PERF_PAGE, 'runner3_perf_settings_page');
}
add_action('admin_menu', 'runner3_perf_admin_menu');

function runner3_perf_settings_page() {
    if (!current_user_can('manage_options')) return;
    $opts = runner3_perf_options();
    ?>
    <div class="wrap">
        <h1>Runner3 Performance Controller</h1>
        <?php settings_errors(); ?>
        <p><strong>Status:</strong> <?php echo $opts['enabled'] ? '<span style="color:#008a20">ACTIVE</span>' : '<span style="color:#b32d2e">DISABLED / ROLLBACK</span>'; ?></p>
        <p>This controller uses WordPress/browser-native loading features. It adds no front-end JavaScript and does not remove original assets.</p>
        <form method="post" action="options.php">
            <?php settings_fields('runner3_perf_group'); ?>
            <table class="form-table" role="presentation">
                <tr><th scope="row">Master switch</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[enabled]" value="1" <?php checked($opts['enabled'], 1); ?>> Enable performance controller</label></td></tr>
                <tr><th scope="row">Smart lazy loading</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[smart_lazy]" value="1" <?php checked($opts['smart_lazy'], 1); ?>> Use native lazy loading for non-critical WordPress media</label><p class="description">LCP/high-priority images are never deliberately marked lazy.</p></td></tr>
                <tr><th scope="row">WordPress eager threshold</th><td><input type="number" min="1" max="6" name="<?php echo RUNNER3_PERF_OPTION; ?>[omit_threshold]" value="<?php echo esc_attr($opts['omit_threshold']); ?>"><p class="description">Number of initial main-content media elements WordPress may keep out of lazy loading. Aggressive default: 1.</p></td></tr>
                <tr><th scope="row">Theme/plugin HTML fallback</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[raw_html_fallback]" value="1" <?php checked($opts['raw_html_fallback'], 1); ?>> Fill missing loading attributes in raw theme/plugin HTML</label><p class="description">Uses the WordPress HTML Tag Processor, not regex-based HTML rewriting.</p></td></tr>
                <tr><th scope="row">Raw HTML eager images</th><td><input type="number" min="1" max="6" name="<?php echo RUNNER3_PERF_OPTION; ?>[raw_eager_count]" value="<?php echo esc_attr($opts['raw_eager_count']); ?>"><p class="description">Conservative safety window for raw theme images before forcing lazy loading. Default: 2.</p></td></tr>
                <tr><th scope="row">Lazy-load iframes</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[lazy_iframes]" value="1" <?php checked($opts['lazy_iframes'], 1); ?>> Add native loading="lazy" to unmarked iframes</label></td></tr>
                <tr><th scope="row">Async image decoding</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[decode_async]" value="1" <?php checked($opts['decode_async'], 1); ?>> Add decoding="async" where not already specified</label></td></tr>
                <tr><th scope="row">Hero/LCP priority</th><td><label><input type="checkbox" name="<?php echo RUNNER3_PERF_OPTION; ?>[hero_priority]" value="1" <?php checked($opts['hero_priority'], 1); ?>> Protect known hero/LCP images from lazy loading and mark high priority</label><p class="description">WordPress core continues to choose high-priority attachment images automatically. This also protects the current site hero.</p></td></tr>
            </table>
            <?php submit_button('Save Performance Settings'); ?>
        </form>
        <hr>
        <h2>Emergency rollback</h2>
        <p>Disables this controller immediately. Media Optimizer, theme files and original images are untouched.</p>
        <p><a class="button" style="color:#b32d2e;border-color:#b32d2e" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=runner3_perf_rollback'), 'runner3_perf_rollback')); ?>">Disable Performance Controller</a></p>
    </div>
    <?php
}

function runner3_perf_rollback() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('runner3_perf_rollback');
    $opts = runner3_perf_options();
    $opts['enabled'] = 0;
    update_option(RUNNER3_PERF_OPTION, $opts, false);
    wp_safe_redirect(add_query_arg(array('page' => RUNNER3_PERF_PAGE, 'runner3_rollback' => 1), admin_url('options-general.php')));
    exit;
}
add_action('admin_post_runner3_perf_rollback', 'runner3_perf_rollback');

function runner3_perf_omit_threshold($threshold) {
    $opts = runner3_perf_options();
    if (!$opts['enabled'] || !$opts['smart_lazy']) return $threshold;
    return (int) $opts['omit_threshold'];
}
add_filter('wp_omit_loading_attr_threshold', 'runner3_perf_omit_threshold', 20);

function runner3_perf_lazy_enabled($default, $tag_name, $context) {
    $opts = runner3_perf_options();
    if (!$opts['enabled'] || !$opts['smart_lazy']) return $default;
    if ($tag_name === 'img') return true;
    if ($tag_name === 'iframe' && $opts['lazy_iframes']) return true;
    return $default;
}
add_filter('wp_lazy_loading_enabled', 'runner3_perf_lazy_enabled', 20, 3);

function runner3_perf_is_current_hero_src($src) {
    if (!$src) return false;
    return (bool) preg_match('~/sites/runner3-factory-smoke-2/(?:responsive-v2/)?offset-demo-01(?:-w[0-9]+)?\.webp(?:[?#].*)?$~i', (string) $src);
}

function runner3_perf_should_skip_raw_image($processor) {
    $src = (string) $processor->get_attribute('src');
    if ($src === '' || stripos($src, 'data:') === 0) return true;
    $class = strtolower((string) $processor->get_attribute('class'));
    if (preg_match('/\b(?:custom-logo|site-logo|avatar|emoji|wp-smiley)\b/', $class)) return true;
    if ($processor->get_attribute('data-runner3-eager') !== null) return true;
    return false;
}

function runner3_perf_optimize_html($html) {
    $opts = runner3_perf_options();
    if (!$opts['enabled'] || !$opts['raw_html_fallback'] || !is_string($html) || $html === '' || stripos($html, '<html') === false) return $html;
    if (!class_exists('WP_HTML_Tag_Processor')) return $html;

    $p = new WP_HTML_Tag_Processor($html);
    $raw_image_count = 0;
    while ($p->next_tag()) {
        $tag = $p->get_tag();
        if ($tag === 'IMG') {
            if (runner3_perf_should_skip_raw_image($p)) continue;
            $raw_image_count++;
            $src = (string) $p->get_attribute('src');
            $fetchpriority = strtolower((string) $p->get_attribute('fetchpriority'));
            $loading = strtolower((string) $p->get_attribute('loading'));
            $is_hero = $opts['hero_priority'] && runner3_perf_is_current_hero_src($src);
            $is_high = $is_hero || $fetchpriority === 'high';

            if ($is_hero) $p->set_attribute('fetchpriority', 'high');
            if ($is_high && $loading === 'lazy') $p->remove_attribute('loading');

            if ($opts['smart_lazy'] && !$is_high && $raw_image_count > (int) $opts['raw_eager_count'] && $loading === '') {
                $p->set_attribute('loading', 'lazy');
            }
            if ($opts['decode_async'] && $p->get_attribute('decoding') === null) {
                $p->set_attribute('decoding', 'async');
            }
        } elseif ($tag === 'IFRAME' && $opts['lazy_iframes']) {
            if ($p->get_attribute('data-runner3-eager') === null && $p->get_attribute('loading') === null) {
                $p->set_attribute('loading', 'lazy');
            }
        }
    }
    return $p->get_updated_html();
}

function runner3_perf_start_buffer() {
    $opts = runner3_perf_options();
    if (!$opts['enabled'] || !$opts['raw_html_fallback'] || is_admin() || wp_doing_ajax() || is_feed() || is_robots() || (defined('REST_REQUEST') && REST_REQUEST)) return;
    if (isset($_SERVER['REQUEST_METHOD']) && $_SERVER['REQUEST_METHOD'] !== 'GET') return;
    ob_start('runner3_perf_optimize_html');
}
add_action('template_redirect', 'runner3_perf_start_buffer', 20);
