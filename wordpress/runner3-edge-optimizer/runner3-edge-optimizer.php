<?php
/**
 * Plugin Name: Runner3 Speed
 * Description: Safe ON/OFF full-page acceleration for WordPress with automatic invalidation and fail-safe bypasses.
 * Version: 1.0.0
 * Author: Runner3
 */
if (!defined('ABSPATH')) exit;

final class Runner3_Speed {
    const VERSION = '1.0.0';
    const ENABLED = 'runner3_speed_enabled';
    const STATUS = 'runner3_speed_status';
    const CRON = 'runner3_speed_prewarm';
    const REMOTE_CRON = 'runner3_edge_optimizer_flush';
    const PENDING = 'runner3_edge_optimizer_pending';
    const ENDPOINT_OPTION = 'runner3_edge_optimizer_endpoint';
    const SECRET_OPTION = 'runner3_edge_optimizer_secret';
    const DROPIN_MARKER = 'RUNNER3_SPEED_DROPIN';
    const WP_CACHE_MARKER = 'RUNNER3_SPEED_WP_CACHE';
    const DEFAULT_ENDPOINT = 'https://runner3-wp-control.ducduy2411.workers.dev/v1/events';

    public static function boot() {
        add_action('admin_menu', [__CLASS__, 'admin_menu']);
        add_action('admin_post_runner3_speed_toggle', [__CLASS__, 'toggle']);
        add_action('admin_post_runner3_speed_test', [__CLASS__, 'test']);
        add_action('template_redirect', [__CLASS__, 'start_capture'], -9999);
        add_action(self::CRON, [__CLASS__, 'prewarm']);
        add_action(self::REMOTE_CRON, [__CLASS__, 'flush_remote']);
        foreach (['save_post', 'before_delete_post', 'wp_update_nav_menu', 'customize_save_after', 'switch_theme', 'edited_term', 'delete_term', 'add_attachment', 'edit_attachment', 'delete_attachment'] as $hook) {
            add_action($hook, [__CLASS__, 'invalidate_hook'], 999, 3);
        }
        add_action('transition_post_status', [__CLASS__, 'status_hook'], 999, 3);
    }

    public static function activate() {
        if (get_option(self::ENABLED, null) === null) add_option(self::ENABLED, '0', '', false);
        self::write_status('off', 'Ready. Turn Performance ON to enable safe page caching.');
    }

    public static function deactivate() { self::disable_engine(false); }

    public static function admin_menu() {
        add_options_page('Runner3 Speed', 'Runner3 Speed', 'manage_options', 'runner3-speed', [__CLASS__, 'page']);
    }

    public static function page() {
        if (!current_user_can('manage_options')) return;
        $enabled = self::enabled();
        $conflict = self::conflict();
        $status = get_option(self::STATUS, []);
        $state = $enabled ? 'ON' : 'OFF';
        $state_color = $enabled ? '#15803d' : '#6b7280';
        $detail = is_array($status) && !empty($status['detail']) ? $status['detail'] : ($enabled ? 'Safe cache active.' : 'WordPress is serving normally.');
        echo '<div class="wrap"><h1>Runner3 Speed</h1>';
        if (isset($_GET['runner3_speed_notice'])) {
            $notice = sanitize_text_field(wp_unslash($_GET['runner3_speed_notice']));
            echo '<div class="notice notice-'.($notice === 'on' || $notice === 'off' || $notice === 'ok' ? 'success' : 'error').' is-dismissible"><p>'.esc_html(self::notice_text($notice)).'</p></div>';
        }
        echo '<div style="max-width:680px;background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:24px;margin-top:20px">';
        echo '<div style="display:flex;align-items:center;justify-content:space-between;gap:16px"><div><div style="font-size:14px;color:#646970">Performance</div><div style="font-size:32px;font-weight:700;color:'.esc_attr($state_color).'">'.esc_html($state).'</div></div>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'"><input type="hidden" name="action" value="runner3_speed_toggle"><input type="hidden" name="enable" value="'.($enabled ? '0' : '1').'">';
        wp_nonce_field('runner3_speed_toggle');
        submit_button($enabled ? 'Turn OFF' : 'Turn ON', $enabled ? 'secondary' : 'primary', 'submit', false);
        echo '</form></div>';
        echo '<hr style="margin:22px 0"><p><strong>Status:</strong> '.esc_html($detail).'</p>';
        echo '<p>✓ Anonymous page cache<br>✓ Login/Admin/API bypass<br>✓ WooCommerce cart/checkout/session bypass<br>✓ Auto purge on content changes<br>✓ OFF = immediate bypass to normal WordPress</p>';
        if ($conflict) echo '<p style="color:#b32d2e"><strong>Safety lock:</strong> '.esc_html($conflict).'</p>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'" style="margin-top:18px"><input type="hidden" name="action" value="runner3_speed_test">';
        wp_nonce_field('runner3_speed_test'); submit_button('Run Health Check', 'secondary', 'submit', false); echo '</form>';
        echo '</div></div>';
    }

    private static function notice_text($notice) {
        $map = [
            'on' => 'Runner3 Speed is ON.',
            'off' => 'Runner3 Speed is OFF. WordPress is serving normally.',
            'ok' => 'Health check passed.',
            'conflict' => 'Runner3 Speed stayed OFF because another page-cache drop-in is already installed.',
            'wp_cache' => 'Runner3 Speed stayed OFF because WP_CACHE could not be enabled safely.',
            'dropin' => 'Runner3 Speed stayed OFF because the cache drop-in could not be installed safely.',
            'failed' => 'Health check failed. Optimization was not forced.',
        ];
        return $map[$notice] ?? 'Runner3 Speed status updated.';
    }

    public static function toggle() {
        if (!current_user_can('manage_options')) wp_die('Forbidden', 403);
        check_admin_referer('runner3_speed_toggle');
        $enable = !empty($_POST['enable']);
        if (!$enable) { self::disable_engine(true); self::redirect('off'); }
        $conflict = self::conflict();
        if ($conflict) { self::write_status('blocked', $conflict); self::redirect('conflict'); }
        if (!self::ensure_wp_cache()) { self::write_status('blocked', 'WP_CACHE could not be enabled without modifying an existing manual setting.'); self::redirect('wp_cache'); }
        if (!self::install_dropin()) { self::write_status('blocked', 'advanced-cache.php could not be installed safely.'); self::redirect('dropin'); }
        self::purge();
        if (!self::write_flag()) { update_option(self::ENABLED, '0', false); self::write_status('blocked', 'Cache directory is not writable.'); self::redirect('failed'); }
        update_option(self::ENABLED, '1', false);
        self::write_status('on', 'Safe full-page cache active. Dynamic and authenticated requests are bypassed.');
        wp_schedule_single_event(time() + 2, self::CRON);
        self::queue_remote('speed:on', ['/'], true, []);
        self::redirect('on');
    }

    public static function test() {
        if (!current_user_can('manage_options')) wp_die('Forbidden', 403);
        check_admin_referer('runner3_speed_test');
        $ok = true; $detail = [];
        if (self::enabled()) {
            $conflict = self::conflict();
            if ($conflict) { $ok = false; $detail[] = $conflict; }
            if (!is_file(self::flag_file())) { $ok = false; $detail[] = 'Enable flag missing.'; }
            if (!self::dropin_is_ours()) { $ok = false; $detail[] = 'Runner3 cache drop-in missing.'; }
        }
        $home = wp_remote_get(add_query_arg('runner3_health', (string) time(), home_url('/')), ['timeout' => 10, 'redirection' => 2, 'headers' => ['Cache-Control' => 'no-cache']]);
        if (is_wp_error($home) || (int) wp_remote_retrieve_response_code($home) < 200 || (int) wp_remote_retrieve_response_code($home) >= 400) { $ok = false; $detail[] = 'Homepage health request failed.'; }
        self::write_status($ok ? (self::enabled() ? 'on' : 'off') : 'degraded', $ok ? (self::enabled() ? 'Health check passed. Cache engine active.' : 'Health check passed. WordPress is serving normally.') : implode(' ', $detail));
        self::redirect($ok ? 'ok' : 'failed');
    }

    private static function redirect($notice) { wp_safe_redirect(add_query_arg('runner3_speed_notice', $notice, admin_url('options-general.php?page=runner3-speed'))); exit; }
    private static function enabled() { return get_option(self::ENABLED, '0') === '1'; }
    private static function cache_dir() { return WP_CONTENT_DIR . '/cache/runner3-speed'; }
    private static function flag_file() { return self::cache_dir() . '/enabled.flag'; }
    private static function dropin_file() { return WP_CONTENT_DIR . '/advanced-cache.php'; }

    private static function write_flag() {
        if (!wp_mkdir_p(self::cache_dir())) return false;
        $tmp = self::flag_file() . '.tmp-' . wp_generate_uuid4();
        $ok = file_put_contents($tmp, self::VERSION . "\n", LOCK_EX) !== false && @rename($tmp, self::flag_file());
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok;
    }

    private static function disable_engine($remote = true) {
        update_option(self::ENABLED, '0', false);
        if (is_file(self::flag_file())) @unlink(self::flag_file());
        self::purge();
        self::write_status('off', 'OFF. Runner3 cache is bypassed; WordPress serves requests normally.');
        if ($remote) self::queue_remote('speed:off', ['/'], true, []);
    }

    private static function conflict() {
        $dropin = self::dropin_file();
        if (is_file($dropin) && !self::dropin_is_ours()) return 'Another advanced-cache.php already owns WordPress page caching. Runner3 will not overwrite it.';
        $config = self::wp_config_path();
        if ($config && is_readable($config)) {
            $text = @file_get_contents($config);
            if (is_string($text) && preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*false\s*\)/i', $text)) return 'WP_CACHE is explicitly disabled in wp-config.php. Runner3 will not override it.';
        }
        return '';
    }

    private static function dropin_is_ours() {
        $file = self::dropin_file();
        if (!is_file($file)) return false;
        $head = @file_get_contents($file, false, null, 0, 4096);
        return is_string($head) && strpos($head, self::DROPIN_MARKER) !== false;
    }

    private static function install_dropin() {
        $target = self::dropin_file();
        if (is_file($target) && !self::dropin_is_ours()) return false;
        $source = plugin_dir_path(__FILE__) . 'dropins/advanced-cache.php';
        if (!is_file($source)) return false;
        $content = file_get_contents($source);
        if (!is_string($content) || strpos($content, self::DROPIN_MARKER) === false) return false;
        $tmp = WP_CONTENT_DIR . '/.runner3-advanced-cache-' . wp_generate_uuid4() . '.tmp';
        if (file_put_contents($tmp, $content, LOCK_EX) === false) return false;
        $ok = @rename($tmp, $target);
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok && self::dropin_is_ours();
    }

    private static function wp_config_path() {
        $paths = [ABSPATH . 'wp-config.php', dirname(ABSPATH) . '/wp-config.php'];
        foreach ($paths as $path) if (is_file($path)) return $path;
        return null;
    }

    private static function ensure_wp_cache() {
        $path = self::wp_config_path();
        if (!$path || !is_readable($path)) return false;
        $content = file_get_contents($path);
        if (!is_string($content) || strpos($content, '<?php') === false) return false;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)/i', $content)) return true;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*false\s*\)/i', $content)) return false;
        if (!is_writable($path)) return false;
        $line = "/* " . self::WP_CACHE_MARKER . " */\ndefine('WP_CACHE', true);\n\n";
        $markers = ["/* That's all, stop editing! Happy publishing. */", "require_once ABSPATH . 'wp-settings.php';", 'require_once ABSPATH . "wp-settings.php";'];
        $updated = null;
        foreach ($markers as $marker) { $pos = strpos($content, $marker); if ($pos !== false) { $updated = substr($content, 0, $pos) . $line . substr($content, $pos); break; } }
        if ($updated === null) return false;
        $tmp = dirname($path) . '/.runner3-wp-config-' . wp_generate_uuid4() . '.tmp';
        if (file_put_contents($tmp, $updated, LOCK_EX) === false) return false;
        $perms = @fileperms($path); if ($perms) @chmod($tmp, $perms & 0777);
        $ok = @rename($tmp, $path);
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok;
    }

    public static function start_capture() { if (self::cacheable_request()) ob_start([__CLASS__, 'capture']); }

    private static function cacheable_request() {
        if (!self::enabled() || !is_file(self::flag_file())) return false;
        if (defined('DONOTCACHEPAGE') && DONOTCACHEPAGE) return false;
        if (is_admin() || wp_doing_ajax() || is_feed() || is_robots() || is_trackback()) return false;
        if (is_user_logged_in() || is_404() || is_search() || is_preview()) return false;
        $method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
        if ($method !== 'GET' || !empty($_SERVER['QUERY_STRING']) || self::has_bypass_cookie()) return false;
        if (function_exists('is_cart') && is_cart()) return false;
        if (function_exists('is_checkout') && is_checkout()) return false;
        if (function_exists('is_account_page') && is_account_page()) return false;
        return true;
    }

    private static function has_bypass_cookie() {
        foreach (array_keys($_COOKIE ?? []) as $name) if (preg_match('/^(wordpress_logged_in_|wordpress_sec_|wp-postpass_|woocommerce_items_in_cart$|woocommerce_cart_hash$|wp_woocommerce_session_|comment_author_)/i', (string) $name)) return true;
        return false;
    }

    public static function capture($html) {
        if (!is_string($html) || strlen($html) < 512 || stripos($html, '<html') === false || http_response_code() !== 200) return $html;
        foreach (headers_list() as $header) {
            if (stripos($header, 'set-cookie:') === 0) return $html;
            if (stripos($header, 'cache-control:') === 0 && preg_match('/\b(?:private|no-store)\b/i', $header)) return $html;
        }
        $file = self::cache_file_for_request();
        if (!$file || !wp_mkdir_p(dirname($file))) return $html;
        $tmp = $file . '.tmp-' . wp_generate_uuid4();
        if (file_put_contents($tmp, $html, LOCK_EX) !== false) {
            @rename($tmp, $file);
            if (!headers_sent()) { header('X-Runner3-Speed: STORE'); header('Cache-Control: public, max-age=60, stale-while-revalidate=30'); }
        } elseif (is_file($tmp)) @unlink($tmp);
        return $html;
    }

    private static function cache_file_for_request() {
        $host = strtolower((string) ($_SERVER['HTTP_HOST'] ?? ''));
        $uri = (string) ($_SERVER['REQUEST_URI'] ?? '/');
        $path = parse_url($uri, PHP_URL_PATH) ?: '/';
        if ($host === '' || $path === '') return null;
        return self::cache_dir() . '/pages/' . hash('sha256', $host . "\n" . $path) . '.html';
    }

    public static function purge() {
        $dir = self::cache_dir() . '/pages';
        if (!is_dir($dir)) return;
        foreach (glob($dir . '/*.html') ?: [] as $file) if (is_file($file)) @unlink($file);
    }

    public static function invalidate_hook() {
        if (!self::enabled()) return;
        self::purge();
        if (!wp_next_scheduled(self::CRON)) wp_schedule_single_event(time() + 3, self::CRON);
        self::queue_remote('content_changed', ['/'], true, []);
    }

    public static function status_hook($new, $old, $post) { if ($new !== $old && $post && !wp_is_post_revision($post->ID)) self::invalidate_hook(); }

    public static function prewarm() {
        if (self::enabled()) wp_remote_get(home_url('/'), ['timeout' => 8, 'redirection' => 2, 'headers' => ['User-Agent' => 'Runner3SpeedPrewarm/' . self::VERSION]]);
    }

    private static function write_status($state, $detail) { update_option(self::STATUS, ['state' => $state, 'detail' => $detail, 'updatedAt' => time()], false); }
    private static function remote_endpoint() { $value = (string) get_option(self::ENDPOINT_OPTION, ''); return strpos($value, 'https://') === 0 ? esc_url_raw($value) : ''; }
    private static function remote_secret() { return trim((string) get_option(self::SECRET_OPTION, '')); }

    private static function queue_remote($reason, $urls = ['/'], $global = false, $media = []) {
        if (self::remote_endpoint() === '' || self::remote_secret() === '') return;
        $q = get_option(self::PENDING, []); if (!is_array($q)) $q = [];
        $q['reasons'] = array_values(array_unique(array_filter(array_merge($q['reasons'] ?? [], [(string) $reason]))));
        $q['urls'] = array_values(array_unique(array_filter(array_merge($q['urls'] ?? [], $urls))));
        $q['global'] = !empty($q['global']) || $global;
        $q['media'] = array_slice(array_merge($q['media'] ?? [], $media), -16);
        update_option(self::PENDING, $q, false);
        if (!wp_next_scheduled(self::REMOTE_CRON)) wp_schedule_single_event(time() + 20, self::REMOTE_CRON);
    }

    public static function flush_remote() {
        $q = get_option(self::PENDING, []); $endpoint = self::remote_endpoint(); $secret = self::remote_secret();
        if (!is_array($q) || empty($q['reasons']) || $endpoint === '' || $secret === '') return;
        $payload = ['op' => 'enqueue', 'source' => 'runner3-speed/' . self::VERSION, 'reason' => $q['reasons'][0], 'reasons' => array_slice($q['reasons'], 0, 16), 'urls' => array_slice($q['urls'] ?? ['/'], 0, 40), 'global' => !empty($q['global']), 'media' => array_slice($q['media'] ?? [], 0, 16)];
        $body = wp_json_encode($payload, JSON_UNESCAPED_SLASHES); $ts = (string) time(); $sig = base64_encode(hash_hmac('sha256', $ts . "\n" . $body, $secret, true));
        $r = wp_remote_post($endpoint, ['timeout' => 8, 'redirection' => 0, 'headers' => ['Content-Type' => 'application/json', 'X-Runner3-Timestamp' => $ts, 'X-Runner3-Signature' => $sig], 'body' => $body, 'data_format' => 'body']);
        if (!is_wp_error($r) && (int) wp_remote_retrieve_response_code($r) >= 200 && (int) wp_remote_retrieve_response_code($r) < 300) delete_option(self::PENDING); else wp_schedule_single_event(time() + 60, self::REMOTE_CRON);
    }
}

register_activation_hook(__FILE__, ['Runner3_Speed', 'activate']);
register_deactivation_hook(__FILE__, ['Runner3_Speed', 'deactivate']);
Runner3_Speed::boot();
