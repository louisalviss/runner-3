<?php
/**
 * Plugin Name: Runner3 Speed
 * Description: One-click, fail-safe WordPress acceleration. Safe guest page cache plus low-risk frontend stabilization; OFF restores the normal WordPress path.
 * Version: 1.1.0
 * Author: Runner3
 */
if (!defined('ABSPATH')) exit;

final class Runner3_Speed {
    const VERSION = '1.1.0';
    const ENABLED = 'runner3_speed_enabled';
    const STATUS = 'runner3_speed_status';
    const FONTS = 'runner3_speed_critical_fonts';
    const DROPIN_MARKER = 'RUNNER3_SPEED_DROPIN';
    const WP_CACHE_MARKER = 'RUNNER3_SPEED_WP_CACHE';

    public static function boot() {
        add_action('admin_menu', [__CLASS__, 'admin_menu']);
        add_action('admin_post_runner3_speed_toggle', [__CLASS__, 'toggle']);
        add_action('wp_head', [__CLASS__, 'critical_font_preloads'], 1);
        add_action('wp_head', [__CLASS__, 'layout_stabilizer'], 99);
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
        $fonts = self::critical_fonts();
        echo '<div class="wrap"><h1>Runner3 Speed</h1><div style="max-width:620px;background:#fff;border:1px solid #dcdcde;border-radius:12px;padding:24px;margin-top:20px">';
        echo '<div style="display:flex;align-items:center;justify-content:space-between;gap:20px"><div><div style="color:#646970;font-size:14px">Performance</div><div style="font-size:34px;font-weight:700;color:'.($on?'#15803d':'#6b7280').'">'.($on?'ON':'OFF').'</div></div>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'"><input type="hidden" name="action" value="runner3_speed_toggle"><input type="hidden" name="enable" value="'.($on?'0':'1').'">';
        wp_nonce_field('runner3_speed_toggle'); submit_button($on ? 'Turn OFF' : 'Turn ON', $on ? 'secondary' : 'primary', 'submit', false); echo '</form></div>';
        echo '<hr style="margin:22px 0"><p><strong>Status:</strong> '.esc_html($detail).'</p>';
        echo '<p>✓ Guest page cache<br>✓ Login/Admin/API bypass<br>✓ Cart/Checkout/session bypass<br>✓ Auto purge after content changes<br>✓ Critical local font preload'.($on && $fonts ? ' ('.count($fonts).')' : '').'<br>✓ Safe layout stabilization for verified theme adapters<br>✓ OFF = normal WordPress path</p>';
        echo '</div></div>';
    }

    public static function toggle() {
        if (!current_user_can('manage_options')) wp_die('Forbidden', 403);
        check_admin_referer('runner3_speed_toggle');
        if (empty($_POST['enable'])) {
            self::disable();
            self::redirect();
        }
        $reason = self::enable();
        self::status($reason === '' ? 'on' : 'blocked', $reason === '' ? 'Performance ON. Safe cache and frontend stabilization active.' : $reason);
        self::redirect();
    }

    private static function redirect() { wp_safe_redirect(admin_url('options-general.php?page=runner3-speed')); exit; }
    private static function enabled() { return get_option(self::ENABLED, '0') === '1'; }
    private static function cache_dir() { return WP_CONTENT_DIR . '/cache/runner3-speed'; }
    private static function flag_file() { return self::cache_dir() . '/enabled.flag'; }
    private static function dropin_file() { return WP_CONTENT_DIR . '/advanced-cache.php'; }

    private static function status($state, $detail) {
        update_option(self::STATUS, ['state'=>$state,'detail'=>$detail,'updatedAt'=>time()], false);
    }

    private static function enable() {
        $conflict = self::conflict();
        if ($conflict) { update_option(self::ENABLED, '0', false); return $conflict; }
        if (!self::ensure_wp_cache()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: WP_CACHE could not be enabled safely.'; }
        if (!self::install_dropin()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: page-cache drop-in could not be installed safely.'; }
        if (!self::write_flag()) { self::rollback_files(); update_option(self::ENABLED, '0', false); return 'Stayed OFF: cache directory is not writable.'; }

        self::discover_critical_fonts();
        update_option(self::ENABLED, '1', false);
        self::purge_pages();
        self::write_flag();
        wp_remote_get(home_url('/'), ['timeout'=>5,'redirection'=>2,'headers'=>['X-Runner3-Prewarm'=>'1']]);
        return '';
    }

    private static function disable() {
        update_option(self::ENABLED, '0', false);
        delete_option(self::FONTS);
        if (is_file(self::flag_file())) @unlink(self::flag_file());
        self::purge_pages();
        self::remove_our_dropin();
        self::remove_wp_cache_marker();
        self::status('off', 'Performance OFF. WordPress is serving normally.');
    }

    private static function rollback_files() {
        delete_option(self::FONTS);
        if (is_file(self::flag_file())) @unlink(self::flag_file());
        self::remove_our_dropin();
        self::remove_wp_cache_marker();
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
        $ok = @rename($tmp, $target);
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok && self::dropin_is_ours();
    }

    private static function remove_our_dropin() {
        if (self::dropin_is_ours()) @unlink(self::dropin_file());
    }

    private static function wp_config_path() {
        foreach ([ABSPATH.'wp-config.php', dirname(ABSPATH).'/wp-config.php'] as $p) if (is_file($p)) return $p;
        return null;
    }

    private static function atomic_replace($path, $content) {
        if (!is_writable($path)) return false;
        $tmp = dirname($path) . '/.runner3-config-' . wp_generate_uuid4() . '.tmp';
        if (@file_put_contents($tmp, $content, LOCK_EX) === false) return false;
        $perms = @fileperms($path); if ($perms) @chmod($tmp, $perms & 0777);
        $ok = @rename($tmp, $path);
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok;
    }

    private static function ensure_wp_cache() {
        $path = self::wp_config_path();
        if (!$path || !is_readable($path)) return false;
        $text = @file_get_contents($path); if (!is_string($text)) return false;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)/i', $text)) return true;
        if (preg_match('/define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*false\s*\)/i', $text)) return false;
        $block = "/* ".self::WP_CACHE_MARKER." */\ndefine('WP_CACHE', true);\n\n";
        $markers = ["/* That's all, stop editing! Happy publishing. */", "require_once ABSPATH . 'wp-settings.php';", 'require_once ABSPATH . "wp-settings.php";'];
        foreach ($markers as $marker) {
            $pos = strpos($text, $marker);
            if ($pos !== false) return self::atomic_replace($path, substr($text,0,$pos).$block.substr($text,$pos));
        }
        return false;
    }

    private static function remove_wp_cache_marker() {
        $path = self::wp_config_path(); if (!$path || !is_readable($path)) return;
        $text = @file_get_contents($path); if (!is_string($text) || strpos($text, self::WP_CACHE_MARKER) === false) return;
        $rx = '/\/\*\s*'.preg_quote(self::WP_CACHE_MARKER,'/').'\s*\*\/\s*define\s*\(\s*[\'\"]WP_CACHE[\'\"]\s*,\s*true\s*\)\s*;\s*/i';
        $new = preg_replace($rx, '', $text, 1);
        if (is_string($new) && $new !== $text) self::atomic_replace($path, $new);
    }

    private static function write_flag() {
        if (!wp_mkdir_p(self::cache_dir())) return false;
        $tmp = self::flag_file().'.tmp-'.wp_generate_uuid4();
        $ok = @file_put_contents($tmp, self::VERSION."\n", LOCK_EX) !== false && @rename($tmp, self::flag_file());
        if (!$ok && is_file($tmp)) @unlink($tmp);
        return $ok;
    }

    private static function frontend_optimizations_allowed() {
        if (!self::enabled() || is_admin() || is_user_logged_in()) return false;
        $method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
        return $method === 'GET' || $method === 'HEAD';
    }

    private static function critical_fonts() {
        $data = get_option(self::FONTS, []);
        if (!is_array($data)) return [];
        $urls = isset($data['urls']) && is_array($data['urls']) ? $data['urls'] : [];
        return array_values(array_filter(array_unique(array_map('esc_url_raw', $urls))));
    }

    public static function critical_font_preloads() {
        if (!self::frontend_optimizations_allowed()) return;
        foreach (array_slice(self::critical_fonts(), 0, 3) as $url) {
            echo '<link rel="preload" href="'.esc_url($url).'" as="font" type="font/woff2" crossorigin>' . "\n";
        }
    }

    private static function absolute_url($url) {
        $url = html_entity_decode(trim((string)$url), ENT_QUOTES | ENT_HTML5, 'UTF-8');
        if ($url === '') return '';
        if (preg_match('#^https?://#i', $url)) return $url;
        $home = wp_parse_url(home_url('/'));
        $scheme = !empty($home['scheme']) ? $home['scheme'] : 'https';
        $host = !empty($home['host']) ? $home['host'] : '';
        $port = !empty($home['port']) ? ':'.$home['port'] : '';
        if ($host === '') return '';
        if (strpos($url, '//') === 0) return $scheme.':'.$url;
        if ($url[0] === '/') return $scheme.'://'.$host.$port.$url;
        return trailingslashit($scheme.'://'.$host.$port).ltrim($url, '/');
    }

    private static function same_origin($url) {
        $a = wp_parse_url($url); $b = wp_parse_url(home_url('/'));
        if (empty($a['host']) || empty($b['host']) || strcasecmp($a['host'], $b['host']) !== 0) return false;
        $ap = isset($a['port']) ? (int)$a['port'] : (isset($a['scheme']) && strtolower($a['scheme']) === 'http' ? 80 : 443);
        $bp = isset($b['port']) ? (int)$b['port'] : (isset($b['scheme']) && strtolower($b['scheme']) === 'http' ? 80 : 443);
        return $ap === $bp;
    }

    private static function discover_critical_fonts() {
        delete_option(self::FONTS);
        $probe = add_query_arg('runner3_speed_discover', rawurlencode(wp_generate_uuid4()), home_url('/'));
        $response = wp_remote_get($probe, ['timeout'=>8,'redirection'=>2,'headers'=>['X-Runner3-Discovery'=>'1']]);
        if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) return;
        $html = wp_remote_retrieve_body($response);
        if (!is_string($html) || strlen($html) < 512) return;

        preg_match_all('/<link\b[^>]*>/i', $html, $tags);
        $css_urls = [];
        foreach ($tags[0] ?? [] as $tag) {
            if (!preg_match('/\brel\s*=\s*([\'\"])(.*?)\1/i', $tag, $rel) || stripos($rel[2], 'stylesheet') === false) continue;
            if (!preg_match('/\bhref\s*=\s*([\'\"])(.*?)\1/i', $tag, $href)) continue;
            $url = self::absolute_url($href[2]);
            $path = (string)wp_parse_url($url, PHP_URL_PATH);
            if ($url && self::same_origin($url) && strpos($path, '/wp-content/fonts/') !== false) $css_urls[] = $url;
        }
        $css_urls = array_slice(array_values(array_unique($css_urls)), 0, 3);
        if (!$css_urls) return;

        $families = [];
        foreach ($css_urls as $css_url) {
            $css_response = wp_remote_get($css_url, ['timeout'=>6,'redirection'=>2]);
            if (is_wp_error($css_response) || wp_remote_retrieve_response_code($css_response) !== 200) continue;
            $css = wp_remote_retrieve_body($css_response);
            if (!is_string($css) || $css === '') continue;
            if (!preg_match_all('/\/\*\s*(latin|vietnamese)\s*\*\/\s*@font-face\s*\{([^}]*)\}/is', $css, $faces, PREG_SET_ORDER)) continue;
            foreach ($faces as $face) {
                if (strtolower($face[1]) !== 'latin') continue;
                $block = $face[2];
                if (!preg_match('/font-family\s*:\s*([\'\"]?)([^;\'\"]+)\1\s*;/i', $block, $fm)) continue;
                if (!preg_match('/url\(\s*([\'\"]?)([^)\'\"]+\.woff2(?:\?[^)\'\"]*)?)\1\s*\)/i', $block, $um)) continue;
                $family = strtolower(trim($fm[2]));
                $font_url = self::absolute_url($um[2]);
                if ($family === '' || isset($families[$family]) || !$font_url || !self::same_origin($font_url)) continue;
                $families[$family] = esc_url_raw($font_url);
                if (count($families) >= 3) break 2;
            }
        }
        if ($families) update_option(self::FONTS, ['urls'=>array_values($families),'updatedAt'=>time()], false);
    }

    private static function inspiro_adapter_allowed() {
        $template = (string)get_template();
        if (strtolower($template) !== 'inspiro') return false;
        $theme = wp_get_theme($template);
        $version = (string)$theme->get('Version');
        return $version === '' || version_compare($version, '2.2.3', '<=');
    }

    public static function layout_stabilizer() {
        if (!self::frontend_optimizations_allowed() || !self::inspiro_adapter_allowed()) return;
        echo "<script id=\"runner3-inspiro-layout-stabilizer\">(function(){var d=false,o;function a(){if(d)return true;var b=document.body;if(!b||b.classList.contains('has-header-image')||b.classList.contains('has-header-video'))return false;var n=document.getElementById('site-navigation'),c=document.getElementById('content');if(!n||!c)return false;var h=Math.ceil(n.getBoundingClientRect().height);if(!(h>0&&h<300))return false;c.style.paddingTop=h+'px';var x=document.querySelector('.custom-header');if(x)x.style.paddingTop=h+'px';d=true;if(o)o.disconnect();return true}o=new MutationObserver(a);o.observe(document.documentElement,{childList:true,subtree:true});if(document.readyState!=='loading')a();else document.addEventListener('DOMContentLoaded',a,{once:true})})();</script>\n";
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
        foreach (array_keys($_COOKIE ?? []) as $name) {
            if (preg_match('/^(wordpress_logged_in_|wordpress_sec_|wp-postpass_|woocommerce_items_in_cart$|woocommerce_cart_hash$|wp_woocommerce_session_|comment_author_)/i', (string)$name)) return true;
        }
        return false;
    }

    public static function capture($html) {
        if (!is_string($html) || strlen($html) < 512 || stripos($html, '<html') === false || http_response_code() !== 200) return $html;
        foreach (headers_list() as $header) {
            if (stripos($header, 'set-cookie:') === 0) return $html;
            if (stripos($header, 'cache-control:') === 0 && preg_match('/\b(?:private|no-store|no-cache)\b/i', $header)) return $html;
        }
        $file = self::cache_file_for_request();
        if (!$file || !wp_mkdir_p(dirname($file))) return $html;
        $tmp = $file.'.tmp-'.wp_generate_uuid4();
        if (@file_put_contents($tmp, $html, LOCK_EX) !== false) {
            if (!@rename($tmp, $file)) {
                @unlink($tmp);
            } elseif (!headers_sent()) {
                header('X-Runner3-Speed: STORE');
                header('X-Runner3-Speed-Version: '.self::VERSION);
            }
        } elseif (is_file($tmp)) @unlink($tmp);
        return $html;
    }

    private static function cache_file_for_request() {
        $host = strtolower((string)($_SERVER['HTTP_HOST'] ?? '')); if ($host === '') return null;
        $path = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH) ?: '/';
        return self::cache_dir().'/pages/'.hash('sha256', 'v110'."\n".$host."\n".$path).'.html';
    }

    public static function invalidate() {
        if (!self::enabled()) return;
        self::purge_pages();
        self::write_flag();
        wp_remote_get(home_url('/'), ['timeout'=>3,'redirection'=>2,'blocking'=>false,'headers'=>['X-Runner3-Prewarm'=>'1']]);
    }

    private static function purge_pages() {
        $dir = self::cache_dir().'/pages';
        if (!is_dir($dir)) return;
        $files = glob($dir.'/*.html');
        if (is_array($files)) foreach ($files as $file) if (is_file($file)) @unlink($file);
    }
}

register_activation_hook(__FILE__, ['Runner3_Speed','activate']);
register_deactivation_hook(__FILE__, ['Runner3_Speed','deactivate']);
Runner3_Speed::boot();
