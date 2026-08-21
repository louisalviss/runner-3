<?php
/**
 * Plugin Name: Runner3 Speed
 * Description: One-click, fail-safe page acceleration with safe frontend optimizations.
 * Version: 1.2.1
 * Author: Runner3
 */
if (!defined('ABSPATH')) exit;

final class Runner3_Speed {
    const VERSION = '1.2.1';
    const CACHE_KEY_VERSION = 'v121';
    const ENABLED = 'runner3_speed_enabled';
    const STATUS = 'runner3_speed_status';
    const DROPIN_MARKER = 'RUNNER3_SPEED_DROPIN';
    const WP_CACHE_MARKER = 'RUNNER3_SPEED_WP_CACHE';

    public static function boot() {
        add_action('admin_menu', [__CLASS__, 'admin_menu']);
        add_action('admin_post_runner3_speed_toggle', [__CLASS__, 'toggle']);
        add_action('template_redirect', [__CLASS__, 'start_capture'], -9999);
        foreach (['save_post','before_delete_post','wp_update_nav_menu','customize_save_after','switch_theme','edited_term','delete_term','add_attachment','edit_attachment','delete_attachment'] as $hook) {
            add_action($hook, [__CLASS__, 'invalidate'], 999, 3);
        }
        add_action('transition_post_status', [__CLASS__, 'invalidate'], 999, 3);
    }

    public static function activate() {
        if (get_option(self::ENABLED, null) === null) add_option(self::ENABLED, '0', '', false);
        self::status('off', 'Ready. Turn Performance ON.');
    }

    public static function deactivate() { self::disable(); }

    public static function admin_menu() {
        add_options_page('Runner3 Speed', 'Runner3 Speed', 'manage_options', 'runner3-speed', [__CLASS__, 'page']);
    }

    public static function page() {
        if (!current_user_can('manage_options')) return;
        $on = self::enabled();
        $s = get_option(self::STATUS, []);
        $detail = is_array($s) && !empty($s['detail']) ? $s['detail'] : ($on ? 'Safe acceleration active.' : 'WordPress is serving normally.');
        echo '<div class="wrap"><h1>Runner3 Speed</h1><div style="max-width:620px;background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:24px;margin-top:20px">';
        echo '<div style="display:flex;align-items:center;justify-content:space-between;gap:20px"><div><div style="color:#646970;font-size:14px">Performance</div><div style="font-size:34px;font-weight:700;color:'.($on?'#15803d':'#6b7280').'">'.($on?'ON':'OFF').'</div></div>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'"><input type="hidden" name="action" value="runner3_speed_toggle"><input type="hidden" name="enable" value="'.($on?'0':'1').'">';
        wp_nonce_field('runner3_speed_toggle'); submit_button($on ? 'Turn OFF' : 'Turn ON', $on ? 'secondary' : 'primary', 'submit', false); echo '</form></div>';
        echo '<hr style="margin:22px 0"><p><strong>Status:</strong> '.esc_html($detail).'</p>';
        echo '<p>✓ Guest page cache<br>✓ Login/Admin/API bypass<br>✓ Cart/Checkout/session bypass<br>✓ Auto purge after content changes<br>✓ Safe lazy-load for iframes when unset<br>✓ Conservative preconnect for third-party origins<br>✓ Version-locked cache files<br>✓ OFF = normal WordPress path</p>';
        echo '</div></div>';
    }

    public static function toggle() {
        if (!current_user_can('manage_options')) wp_die('Forbidden', 403);
        check_admin_referer('runner3_speed_toggle');
        if (empty($_POST['enable'])) { self::disable(); self::redirect(); }
        $reason = self::enable();
        self::status($reason === '' ? 'on' : 'blocked', $reason === '' ? 'Performance ON. Safe cache + frontend optimization active.' : $reason);
        self::redirect();
    }

    private static function redirect() { wp_safe_redirect(admin_url('options-general.php?page=runner3-speed')); exit; }
    private static function enabled() { return get_option(self::ENABLED, '0') === '1'; }
    private static function cache_dir() { return WP_CONTENT_DIR . '/cache/runner3-speed'; }
    private static function flag_file() { return self::cache_dir() . '/enabled.flag'; }
    private static function dropin_file() { return WP_CONTENT_DIR . '/advanced-cache.php'; }
    private static function status($state, $detail) { update_option(self::STATUS, ['state'=>$state,'detail'=>$detail,'updatedAt'=>time()], false); }

    private static function enable() {
        $conflict = self::conflict();
        if ($conflict) { update_option(self::ENABLED, '0', false); return $conflict; }
        if (!self::ensure_wp_cache()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: WP_CACHE could not be enabled safely.'; }
        if (!self::install_dropin()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: page-cache drop-in could not be installed safely.'; }
        if (!self::write_flag()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: cache directory is not writable.'; }
        update_option(self::ENABLED, '1', false);
        self::purge_pages(); self::write_flag();
        wp_remote_get(home_url('/'), ['timeout'=>5,'redirection'=>2,'headers'=>['X-Runner3-Prewarm'=>'1']]);
        return '';
    }

    private static function disable() {
        update_option(self::ENABLED, '0', false);
        if (is_file(self::flag_file())) @unlink(self::flag_file());
        self::purge_pages(); self::remove_our_dropin(); self::remove_wp_cache_marker();
        self::status('off', 'Performance OFF. WordPress is serving normally.');
    }

    private static function rollback_files() {
        if (is_file(self::flag_file())) @unlink(self::flag_file());
        self::remove_our_dropin(); self::remove_wp_cache_marker();
    }

    private static function conflict() {
        if (is_file(self::dropin_file()) && !self::dropin_is_ours()) return 'Stayed OFF: another page-cache drop-in already exists. Runner3 will not overwrite it.';
        $config = self::wp_config_path();
        if (!$config || !is_readable($config)) return 'Stayed OFF: wp-config.php is not readable.';
        $text = @file_get_contents($config);
        if (is_string($text) && preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*false\s*\)/i', $text)) return 'Stayed OFF: WP_CACHE is explicitly disabled. Runner3 will not override it.';
        return '';
    }

    private static function dropin_is_ours() {
        $head = is_file(self::dropin_file()) ? @file_get_contents(self::dropin_file(), false, null, 0, 4096) : '';
        return is_string($head) && strpos($head, self::DROPIN_MARKER) !== false;
    }

    private static function install_dropin() {
        $target = self::dropin_file();
        if (is_file($target) && !self::dropin_is_ours()) return false;
        $source = plugin_dir_path(__FILE__) . 'dropins/advanced-cache.php';
        $content = is_file($source) ? @file_get_contents($source) : false;
        if (!is_string($content) || strpos($content, self::DROPIN_MARKER) === false) return false;
        $tmp = WP_CONTENT_DIR . '/.runner3-cache-' . wp_generate_uuid4() . '.tmp';
        if (@file_put_contents($tmp, $content, LOCK_EX) === false) return false;
        $ok = @rename($tmp, $target); if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok && self::dropin_is_ours();
    }

    private static function remove_our_dropin() { if (self::dropin_is_ours()) @unlink(self::dropin_file()); }
    private static function wp_config_path() { foreach ([ABSPATH.'wp-config.php', dirname(ABSPATH).'/wp-config.php'] as $p) if (is_file($p)) return $p; return null; }

    private static function atomic_replace($path, $content) {
        if (!is_writable($path)) return false;
        $tmp = dirname($path) . '/.runner3-config-' . wp_generate_uuid4() . '.tmp';
        if (@file_put_contents($tmp, $content, LOCK_EX) === false) return false;
        $perms = @fileperms($path); if ($perms) @chmod($tmp, $perms & 0777);
        $ok = @rename($tmp, $path); if (!$ok && is_file($tmp)) @unlink($tmp); return $ok;
    }

    private static function ensure_wp_cache() {
        $path = self::wp_config_path(); if (!$path || !is_readable($path)) return false;
        $text = @file_get_contents($path); if (!is_string($text)) return false;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)/i', $text)) return true;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*false\s*\)/i', $text)) return false;
        $block = "/* ".self::WP_CACHE_MARKER." */\ndefine('WP_CACHE', true);\n\n";
        foreach (["/* That's all, stop editing! Happy publishing. */", "require_once ABSPATH . 'wp-settings.php';", 'require_once ABSPATH . "wp-settings.php";'] as $marker) {
            $pos = strpos($text, $marker); if ($pos !== false) return self::atomic_replace($path, substr($text,0,$pos).$block.substr($text,$pos));
        }
        return false;
    }

    private static function remove_wp_cache_marker() {
        $path = self::wp_config_path(); if (!$path || !is_readable($path)) return;
        $text = @file_get_contents($path); if (!is_string($text) || strpos($text, self::WP_CACHE_MARKER) === false) return;
        $rx = '/\/\*\s*'.preg_quote(self::WP_CACHE_MARKER,'/').'\s*\*\/\s*define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)\s*;\s*/i';
        $new = preg_replace($rx, '', $text, 1); if (is_string($new) && $new !== $text) self::atomic_replace($path, $new);
    }

    private static function write_flag() {
        if (!wp_mkdir_p(self::cache_dir())) return false;
        $tmp = self::flag_file().'.tmp-'.wp_generate_uuid4();
        $ok = @file_put_contents($tmp, self::VERSION."\n", LOCK_EX) !== false && @rename($tmp, self::flag_file());
        if (!$ok && is_file($tmp)) @unlink($tmp); return $ok;
    }

    public static function start_capture() { if (self::cacheable_request()) ob_start([__CLASS__, 'capture']); }

    private static function cacheable_request() {
        if (!self::enabled() || !is_file(self::flag_file())) return false;
        if (defined('DONOTCACHEPAGE') && DONOTCACHEPAGE) return false;
        if (is_admin() || wp_doing_ajax() || is_feed() || is_robots() || is_trackback()) return false;
        if (is_user_logged_in() || is_404() || is_search() || is_preview() || post_password_required()) return false;
        if (strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET' || !empty($_SERVER['QUERY_STRING']) || self::has_bypass_cookie()) return false;
        if (function_exists('is_cart') && is_cart()) return false;
        if (function_exists('is_checkout') && is_checkout()) return false;
        if (function_exists('is_account_page') && is_account_page()) return false;
        return true;
    }

    private static function has_bypass_cookie() {
        foreach (array_keys($_COOKIE ?? []) as $name) if (preg_match('/^(wordpress_logged_in_|wordpress_sec_|wp-postpass_|woocommerce_items_in_cart$|woocommerce_cart_hash$|wp_woocommerce_session_|comment_author_)/i', (string)$name)) return true;
        return false;
    }

    private static function safe_frontend_optimize($html) {
        if (!is_string($html) || $html === '' || !class_exists('WP_HTML_Tag_Processor')) return $html;

        // Preserve WordPress/theme image loading and priority decisions. DOM order
        // is not a reliable LCP signal (the first image is commonly a logo).
        $p = new WP_HTML_Tag_Processor($html);
        while ($p->next_tag('iframe')) {
            if ($p->get_attribute('loading') === null) $p->set_attribute('loading', 'lazy');
        }
        $html = $p->get_updated_html();

        // Add only conservative connection hints for origins already referenced
        // by page markup. Never reorder, combine, defer, or delay CSS/JS here.
        $site_host = strtolower((string)wp_parse_url(home_url('/'), PHP_URL_HOST));
        $origins = [];
        if (preg_match_all('/<(?:script|link|img|iframe)\b[^>]+(?:src|href)=["\'](https?:\/\/[^"\']+)["\']/i', $html, $m)) {
            foreach ($m[1] as $url) {
                $scheme = strtolower((string)wp_parse_url($url, PHP_URL_SCHEME));
                $host = strtolower((string)wp_parse_url($url, PHP_URL_HOST));
                if (!$host || $host === $site_host || !in_array($scheme, ['http','https'], true)) continue;
                $origins[$scheme.'://'.$host] = true;
                if (count($origins) >= 3) break;
            }
        }
        $hints = [];
        foreach (array_keys($origins) as $origin) {
            $e = esc_url($origin);
            $host = (string)wp_parse_url($e, PHP_URL_HOST);
            if ($e === '' || $host === '') continue;
            $hints[] = '<link rel="preconnect" href="'.esc_attr($e).'" crossorigin data-runner3-speed="preconnect">';
            $hints[] = '<link rel="dns-prefetch" href="//'.esc_attr($host).'" data-runner3-speed="dns">';
        }
        if ($hints && stripos($html, '</head>') !== false) {
            $html = preg_replace('/<\/head>/i', implode('', $hints).'</head>', $html, 1);
        }
        return $html;
    }

    public static function capture($html) {
        if (!is_string($html) || strlen($html) < 512 || stripos($html, '<html') === false || http_response_code() !== 200) return $html;
        foreach (headers_list() as $header) {
            if (stripos($header, 'set-cookie:') === 0) return $html;
            if (stripos($header, 'cache-control:') === 0 && preg_match('/\b(?:private|no-store|no-cache)\b/i', $header)) return $html;
        }
        $html = self::safe_frontend_optimize($html);
        $file = self::cache_file_for_request(); if (!$file || !wp_mkdir_p(dirname($file))) return $html;
        $tmp = $file.'.tmp-'.wp_generate_uuid4();
        if (@file_put_contents($tmp, $html, LOCK_EX) !== false) {
            if (!@rename($tmp, $file)) @unlink($tmp);
            elseif (!headers_sent()) { header('X-Runner3-Speed: STORE'); header('X-Runner3-Speed-Version: '.self::VERSION); }
        } elseif (is_file($tmp)) @unlink($tmp);
        return $html;
    }

    private static function cache_file_for_request() {
        $host = strtolower((string)($_SERVER['HTTP_HOST'] ?? '')); if ($host === '') return null;
        $path = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH) ?: '/';
        return self::cache_dir().'/pages/'.hash('sha256', self::CACHE_KEY_VERSION."\n".$host."\n".$path).'.html';
    }

    public static function invalidate() {
        if (!self::enabled()) return;
        self::purge_pages(); self::write_flag();
        wp_remote_get(home_url('/'), ['timeout'=>3,'redirection'=>2,'blocking'=>false,'headers'=>['X-Runner3-Prewarm'=>'1']]);
    }

    private static function purge_pages() {
        $dir = self::cache_dir().'/pages'; if (!is_dir($dir)) return;
        $files = glob($dir.'/*.html'); if (is_array($files)) foreach ($files as $file) if (is_file($file)) @unlink($file);
    }
}

register_activation_hook(__FILE__, ['Runner3_Speed','activate']);
register_deactivation_hook(__FILE__, ['Runner3_Speed','deactivate']);
Runner3_Speed::boot();
