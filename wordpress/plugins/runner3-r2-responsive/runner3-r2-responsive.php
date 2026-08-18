<?php
/**
 * Plugin Name: Runner3 Media Optimizer
 * Description: Automatic responsive WebP generation, optional Cloudflare R2 offload, native WordPress srcset integration, backfill and instant rollback. Keeps the existing OFFSET R2 bridge for compatibility.
 * Version: 2.0.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) {
    exit;
}

const RUNNER3_MEDIA_OPTION = 'runner3_media_optimizer';
const RUNNER3_MEDIA_META = '_runner3_media_variants';
const RUNNER3_MEDIA_LAST_ERROR = '_runner3_media_last_error';
const RUNNER3_MEDIA_PAGE = 'runner3-media-optimizer';

// Compatibility bridge for the current OFFSET demo assets. New Media Library
// uploads use native WordPress attachment hooks below and do not depend on this.
const RUNNER3_LEGACY_R2_ORIGIN = 'https://pub-f6e5190178814cd5be8f1eb531f1a164.r2.dev';
const RUNNER3_LEGACY_R2_SITE_PREFIX = '/sites/runner3-factory-smoke-2/';
const RUNNER3_LEGACY_R2_VARIANT_DIR = 'responsive-v2/';

function runner3_media_defaults() {
    return array(
        'enabled' => 1,
        'auto_new' => 1,
        'rewrite_srcset' => 1,
        'widths' => '360,480,640,960,1280',
        'quality' => 78,
        'sizes' => '(max-width: 767px) 92vw, 1100px',
        'r2_enabled' => 0,
        'r2_account_id' => '',
        'r2_bucket' => '',
        'r2_access_key' => '',
        'r2_secret' => '',
        'r2_public_base' => '',
        'r2_prefix' => 'runner3-media',
        'legacy_bridge' => 1,
    );
}

function runner3_media_options() {
    return wp_parse_args((array) get_option(RUNNER3_MEDIA_OPTION, array()), runner3_media_defaults());
}

function runner3_media_widths($raw = null) {
    $opts = runner3_media_options();
    $raw = $raw === null ? $opts['widths'] : $raw;
    $parts = preg_split('/[^0-9]+/', (string) $raw);
    $widths = array();
    foreach ((array) $parts as $part) {
        $w = absint($part);
        if ($w >= 160 && $w <= 4096) {
            $widths[$w] = $w;
        }
    }
    ksort($widths, SORT_NUMERIC);
    return array_values($widths ?: array(360, 480, 640, 960, 1280));
}

function runner3_media_encrypt($plain) {
    $plain = (string) $plain;
    if ($plain === '') return '';
    $key = hash('sha256', wp_salt('auth'), true);
    if (function_exists('sodium_crypto_secretbox')) {
        $nonce = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
        return 'sbox:' . base64_encode($nonce . sodium_crypto_secretbox($plain, $nonce, $key));
    }
    if (function_exists('openssl_encrypt')) {
        $iv = random_bytes(12);
        $tag = '';
        $cipher = openssl_encrypt($plain, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
        if ($cipher !== false) return 'gcm:' . base64_encode($iv . $tag . $cipher);
    }
    return '';
}

function runner3_media_decrypt($stored) {
    $stored = (string) $stored;
    if ($stored === '') return '';
    $key = hash('sha256', wp_salt('auth'), true);
    if (strpos($stored, 'sbox:') === 0 && function_exists('sodium_crypto_secretbox_open')) {
        $raw = base64_decode(substr($stored, 5), true);
        if ($raw === false || strlen($raw) <= SODIUM_CRYPTO_SECRETBOX_NONCEBYTES) return '';
        $nonce = substr($raw, 0, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
        $plain = sodium_crypto_secretbox_open(substr($raw, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES), $nonce, $key);
        return $plain === false ? '' : $plain;
    }
    if (strpos($stored, 'gcm:') === 0 && function_exists('openssl_decrypt')) {
        $raw = base64_decode(substr($stored, 4), true);
        if ($raw === false || strlen($raw) <= 28) return '';
        $plain = openssl_decrypt(substr($raw, 28), 'aes-256-gcm', $key, OPENSSL_RAW_DATA, substr($raw, 0, 12), substr($raw, 12, 16));
        return $plain === false ? '' : $plain;
    }
    return '';
}

function runner3_media_sanitize_options($input) {
    $old = runner3_media_options();
    $input = (array) $input;
    $out = runner3_media_defaults();
    foreach (array('enabled', 'auto_new', 'rewrite_srcset', 'r2_enabled', 'legacy_bridge') as $key) {
        $out[$key] = empty($input[$key]) ? 0 : 1;
    }
    $out['widths'] = implode(',', runner3_media_widths(isset($input['widths']) ? $input['widths'] : ''));
    $out['quality'] = min(95, max(45, absint(isset($input['quality']) ? $input['quality'] : 78)));
    $out['sizes'] = sanitize_text_field(isset($input['sizes']) ? $input['sizes'] : $out['sizes']);
    $out['r2_account_id'] = preg_replace('/[^a-zA-Z0-9]/', '', isset($input['r2_account_id']) ? $input['r2_account_id'] : '');
    $out['r2_bucket'] = sanitize_text_field(isset($input['r2_bucket']) ? $input['r2_bucket'] : '');
    $out['r2_access_key'] = sanitize_text_field(isset($input['r2_access_key']) ? $input['r2_access_key'] : '');
    $out['r2_public_base'] = untrailingslashit(esc_url_raw(isset($input['r2_public_base']) ? $input['r2_public_base'] : ''));
    $out['r2_prefix'] = trim(sanitize_text_field(isset($input['r2_prefix']) ? $input['r2_prefix'] : 'runner3-media'), '/');
    $new_secret = isset($input['r2_secret_plain']) ? trim((string) $input['r2_secret_plain']) : '';
    $out['r2_secret'] = $new_secret !== '' ? runner3_media_encrypt($new_secret) : (isset($old['r2_secret']) ? $old['r2_secret'] : '');
    if ($out['r2_enabled'] && (!$out['r2_account_id'] || !$out['r2_bucket'] || !$out['r2_access_key'] || !$out['r2_secret'] || !$out['r2_public_base'])) {
        $out['r2_enabled'] = 0;
        add_settings_error(RUNNER3_MEDIA_OPTION, 'runner3_r2_incomplete', 'R2 offload was left disabled because its credentials/public URL are incomplete.', 'warning');
    }
    return $out;
}

function runner3_media_register_settings() {
    register_setting('runner3_media_group', RUNNER3_MEDIA_OPTION, array('sanitize_callback' => 'runner3_media_sanitize_options'));
}
add_action('admin_init', 'runner3_media_register_settings');

function runner3_media_admin_menu() {
    add_options_page('Runner3 Media Optimizer', 'Runner3 Media', 'manage_options', RUNNER3_MEDIA_PAGE, 'runner3_media_settings_page');
}
add_action('admin_menu', 'runner3_media_admin_menu');

function runner3_media_stats() {
    global $wpdb;
    $total = (int) $wpdb->get_var("SELECT COUNT(ID) FROM {$wpdb->posts} WHERE post_type='attachment' AND post_mime_type LIKE 'image/%'");
    $optimized = (int) $wpdb->get_var($wpdb->prepare("SELECT COUNT(DISTINCT post_id) FROM {$wpdb->postmeta} WHERE meta_key=%s", RUNNER3_MEDIA_META));
    return array($total, $optimized, max(0, $total - $optimized));
}

function runner3_media_settings_page() {
    if (!current_user_can('manage_options')) return;
    $opts = runner3_media_options();
    list($total, $optimized, $pending) = runner3_media_stats();
    $webp = function_exists('wp_image_editor_supports') ? wp_image_editor_supports(array('mime_type' => 'image/webp')) : false;
    ?>
    <div class="wrap">
        <h1>Runner3 Media Optimizer</h1>
        <?php settings_errors(); ?>
        <p><strong>Status:</strong> <?php echo $opts['enabled'] ? '<span style="color:#008a20">ACTIVE</span>' : '<span style="color:#b32d2e">ROLLBACK / DISABLED</span>'; ?> &nbsp; | &nbsp; WebP editor: <?php echo $webp ? 'available' : 'not available'; ?></p>
        <p><strong>Media Library:</strong> <?php echo esc_html($optimized); ?> optimized / <?php echo esc_html($total); ?> images; <?php echo esc_html($pending); ?> pending.</p>
        <form method="post" action="options.php">
            <?php settings_fields('runner3_media_group'); ?>
            <table class="form-table" role="presentation">
                <tr><th scope="row">Master switch</th><td><label><input type="checkbox" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[enabled]" value="1" <?php checked($opts['enabled'], 1); ?>> Enable optimizer</label><p class="description">Turn this off for an instant safe rollback. Original WordPress images are never deleted.</p></td></tr>
                <tr><th scope="row">New uploads</th><td><label><input type="checkbox" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[auto_new]" value="1" <?php checked($opts['auto_new'], 1); ?>> Automatically create optimized variants when an image is uploaded</label></td></tr>
                <tr><th scope="row">Responsive delivery</th><td><label><input type="checkbox" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[rewrite_srcset]" value="1" <?php checked($opts['rewrite_srcset'], 1); ?>> Add Runner3 variants to native WordPress srcset</label></td></tr>
                <tr><th scope="row">Widths</th><td><input class="regular-text" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[widths]" value="<?php echo esc_attr($opts['widths']); ?>"><p class="description">Comma-separated pixels. Default: 360,480,640,960,1280.</p></td></tr>
                <tr><th scope="row">WebP quality</th><td><input type="number" min="45" max="95" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[quality]" value="<?php echo esc_attr($opts['quality']); ?>"></td></tr>
                <tr><th scope="row">Default sizes</th><td><input class="large-text" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[sizes]" value="<?php echo esc_attr($opts['sizes']); ?>"></td></tr>
                <tr><th scope="row">Cloudflare R2</th><td><label><input type="checkbox" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_enabled]" value="1" <?php checked($opts['r2_enabled'], 1); ?>> Offload generated variants to R2</label><p class="description">Optional. Local optimized files remain as fallback. R2 only becomes active when all fields below are configured.</p></td></tr>
                <tr><th scope="row">R2 Account ID</th><td><input class="regular-text" autocomplete="off" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_account_id]" value="<?php echo esc_attr($opts['r2_account_id']); ?>"></td></tr>
                <tr><th scope="row">R2 Bucket</th><td><input class="regular-text" autocomplete="off" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_bucket]" value="<?php echo esc_attr($opts['r2_bucket']); ?>"></td></tr>
                <tr><th scope="row">R2 Access Key ID</th><td><input class="regular-text" autocomplete="off" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_access_key]" value="<?php echo esc_attr($opts['r2_access_key']); ?>"></td></tr>
                <tr><th scope="row">R2 Secret Access Key</th><td><input class="regular-text" type="password" autocomplete="new-password" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_secret_plain]" value="" placeholder="<?php echo empty($opts['r2_secret']) ? 'Not set' : 'Stored encrypted — leave blank to keep'; ?>"></td></tr>
                <tr><th scope="row">R2 Public Base URL</th><td><input class="large-text" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_public_base]" value="<?php echo esc_attr($opts['r2_public_base']); ?>" placeholder="https://pub-....r2.dev or custom CDN domain"></td></tr>
                <tr><th scope="row">R2 Prefix</th><td><input class="regular-text" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[r2_prefix]" value="<?php echo esc_attr($opts['r2_prefix']); ?>"></td></tr>
                <tr><th scope="row">Current OFFSET compatibility</th><td><label><input type="checkbox" name="<?php echo RUNNER3_MEDIA_OPTION; ?>[legacy_bridge]" value="1" <?php checked($opts['legacy_bridge'], 1); ?>> Keep the existing 8-image R2 bridge active</label><p class="description">Temporary compatibility layer for the current theme demo. New uploads use native attachment hooks instead.</p></td></tr>
            </table>
            <?php submit_button('Save Media Optimizer Settings'); ?>
        </form>
        <hr>
        <h2>One-time existing-media backfill</h2>
        <p>Processes up to 10 unoptimized Media Library images per click. New uploads do not need this; they are automatic.</p>
        <p><a class="button button-secondary" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=runner3_media_backfill'), 'runner3_media_backfill')); ?>">Optimize next 10 existing images</a></p>
        <h2>Emergency rollback</h2>
        <p>This disables delivery/generation immediately without deleting originals or generated files.</p>
        <p><a class="button" style="color:#b32d2e;border-color:#b32d2e" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=runner3_media_rollback'), 'runner3_media_rollback')); ?>">Disable optimizer now</a></p>
    </div>
    <?php
}

function runner3_media_is_supported_attachment($attachment_id) {
    $mime = (string) get_post_mime_type($attachment_id);
    if (!in_array($mime, array('image/jpeg', 'image/png', 'image/webp'), true)) return false;
    $file = get_attached_file($attachment_id);
    return $file && is_file($file);
}

function runner3_media_hmac($key, $data) {
    return hash_hmac('sha256', $data, $key, true);
}

function runner3_media_r2_put($file, $object_key, $content_type) {
    $opts = runner3_media_options();
    $secret = runner3_media_decrypt($opts['r2_secret']);
    if (!$secret) return new WP_Error('r2_secret', 'R2 secret cannot be decrypted.');
    $body = file_get_contents($file);
    if ($body === false) return new WP_Error('r2_read', 'Could not read generated image.');
    $account = $opts['r2_account_id'];
    $bucket = $opts['r2_bucket'];
    $access = $opts['r2_access_key'];
    $host = $account . '.r2.cloudflarestorage.com';
    $encode = function($part) { return rawurlencode($part); };
    $segments = array_map($encode, explode('/', trim($object_key, '/')));
    $uri = '/' . rawurlencode($bucket) . '/' . implode('/', $segments);
    $payload_hash = hash('sha256', $body);
    $amz_date = gmdate('Ymd\\THis\\Z');
    $date = substr($amz_date, 0, 8);
    $canonical_headers = 'content-type:' . $content_type . "\n" . 'host:' . $host . "\n" . 'x-amz-content-sha256:' . $payload_hash . "\n" . 'x-amz-date:' . $amz_date . "\n";
    $signed_headers = 'content-type;host;x-amz-content-sha256;x-amz-date';
    $canonical_request = "PUT\n" . $uri . "\n\n" . $canonical_headers . "\n" . $signed_headers . "\n" . $payload_hash;
    $scope = $date . '/auto/s3/aws4_request';
    $string_to_sign = "AWS4-HMAC-SHA256\n" . $amz_date . "\n" . $scope . "\n" . hash('sha256', $canonical_request);
    $k_date = runner3_media_hmac('AWS4' . $secret, $date);
    $k_region = runner3_media_hmac($k_date, 'auto');
    $k_service = runner3_media_hmac($k_region, 's3');
    $k_signing = runner3_media_hmac($k_service, 'aws4_request');
    $signature = hash_hmac('sha256', $string_to_sign, $k_signing);
    $authorization = 'AWS4-HMAC-SHA256 Credential=' . $access . '/' . $scope . ', SignedHeaders=' . $signed_headers . ', Signature=' . $signature;
    $response = wp_remote_request('https://' . $host . $uri, array(
        'method' => 'PUT',
        'timeout' => 45,
        'headers' => array(
            'Content-Type' => $content_type,
            'Host' => $host,
            'X-Amz-Content-Sha256' => $payload_hash,
            'X-Amz-Date' => $amz_date,
            'Authorization' => $authorization,
        ),
        'body' => $body,
    ));
    if (is_wp_error($response)) return $response;
    $code = (int) wp_remote_retrieve_response_code($response);
    if ($code < 200 || $code >= 300) return new WP_Error('r2_http', 'R2 PUT failed with HTTP ' . $code . '.');
    return trailingslashit($opts['r2_public_base']) . ltrim($object_key, '/');
}

function runner3_media_process_attachment($attachment_id, $force = false) {
    $opts = runner3_media_options();
    if (!$opts['enabled'] || !runner3_media_is_supported_attachment($attachment_id)) return false;
    if (!$force && get_post_meta($attachment_id, RUNNER3_MEDIA_META, true)) return true;
    if (function_exists('wp_image_editor_supports') && !wp_image_editor_supports(array('mime_type' => 'image/webp'))) {
        update_post_meta($attachment_id, RUNNER3_MEDIA_LAST_ERROR, 'WordPress image editor has no WebP support.');
        return false;
    }
    $source = get_attached_file($attachment_id);
    $size = @getimagesize($source);
    if (!$size || empty($size[0]) || empty($size[1])) return false;
    $source_w = (int) $size[0];
    $source_h = (int) $size[1];
    $uploads = wp_get_upload_dir();
    $relative_dir = trim(str_replace(wp_normalize_path($uploads['basedir']), '', wp_normalize_path(dirname($source))), '/');
    $stem = pathinfo($source, PATHINFO_FILENAME);
    $variants = array();
    $errors = array();
    foreach (runner3_media_widths() as $width) {
        if ($width > $source_w) continue;
        $height = max(1, (int) round($source_h * ($width / $source_w)));
        $editor = wp_get_image_editor($source);
        if (is_wp_error($editor)) { $errors[] = $editor->get_error_message(); continue; }
        if (method_exists($editor, 'set_quality')) $editor->set_quality((int) $opts['quality']);
        $resized = $editor->resize($width, $height, false);
        if (is_wp_error($resized)) { $errors[] = $resized->get_error_message(); continue; }
        $filename = sanitize_file_name($stem . '-r3-w' . $width . '.webp');
        $dest = trailingslashit(dirname($source)) . $filename;
        $saved = $editor->save($dest, 'image/webp');
        if (is_wp_error($saved) || empty($saved['path'])) { $errors[] = is_wp_error($saved) ? $saved->get_error_message() : 'save failed'; continue; }
        $local_url = trailingslashit($uploads['baseurl']) . ($relative_dir ? trailingslashit($relative_dir) : '') . rawurlencode($filename);
        $row = array(
            'width' => $width,
            'height' => isset($saved['height']) ? (int) $saved['height'] : $height,
            'bytes' => is_file($saved['path']) ? (int) filesize($saved['path']) : 0,
            'local_file' => wp_normalize_path($saved['path']),
            'local_url' => $local_url,
            'remote_url' => '',
        );
        if ($opts['r2_enabled']) {
            $prefix = trim($opts['r2_prefix'], '/');
            $object = ($prefix ? $prefix . '/' : '') . ($relative_dir ? trim($relative_dir, '/') . '/' : '') . $attachment_id . '/' . $filename;
            $remote = runner3_media_r2_put($saved['path'], $object, 'image/webp');
            if (is_wp_error($remote)) $errors[] = $remote->get_error_message(); else $row['remote_url'] = $remote;
        }
        $variants[(string) $width] = $row;
    }
    if (!$variants) {
        update_post_meta($attachment_id, RUNNER3_MEDIA_LAST_ERROR, implode(' | ', array_unique($errors ?: array('No eligible variants were generated.'))));
        return false;
    }
    ksort($variants, SORT_NUMERIC);
    update_post_meta($attachment_id, RUNNER3_MEDIA_META, array(
        'version' => 2,
        'generated_at' => gmdate('c'),
        'source_width' => $source_w,
        'source_height' => $source_h,
        'quality' => (int) $opts['quality'],
        'variants' => $variants,
    ));
    delete_post_meta($attachment_id, RUNNER3_MEDIA_LAST_ERROR);
    return true;
}

function runner3_media_on_metadata($metadata, $attachment_id, $context) {
    $opts = runner3_media_options();
    if ($opts['enabled'] && $opts['auto_new'] && $context === 'create') runner3_media_process_attachment($attachment_id, true);
    return $metadata;
}
add_filter('wp_generate_attachment_metadata', 'runner3_media_on_metadata', 20, 3);

function runner3_media_srcset($sources, $size_array, $image_src, $image_meta, $attachment_id) {
    $opts = runner3_media_options();
    if (!$opts['enabled'] || !$opts['rewrite_srcset'] || !$attachment_id) return $sources;
    $stored = get_post_meta($attachment_id, RUNNER3_MEDIA_META, true);
    if (empty($stored['variants']) || !is_array($stored['variants'])) return $sources;
    foreach ($stored['variants'] as $row) {
        $w = isset($row['width']) ? absint($row['width']) : 0;
        if (!$w) continue;
        $url = $opts['r2_enabled'] && !empty($row['remote_url']) ? $row['remote_url'] : (isset($row['local_url']) ? $row['local_url'] : '');
        if (!$url) continue;
        $sources[$w] = array('url' => $url, 'descriptor' => 'w', 'value' => $w);
    }
    ksort($sources, SORT_NUMERIC);
    return $sources;
}
add_filter('wp_calculate_image_srcset', 'runner3_media_srcset', 20, 5);

function runner3_media_sizes($sizes, $size, $image_src, $image_meta, $attachment_id) {
    $opts = runner3_media_options();
    if (!$opts['enabled'] || !$attachment_id || !get_post_meta($attachment_id, RUNNER3_MEDIA_META, true)) return $sizes;
    return $opts['sizes'] ?: $sizes;
}
add_filter('wp_calculate_image_sizes', 'runner3_media_sizes', 20, 5);

function runner3_media_resource_hints($urls, $relation_type) {
    $opts = runner3_media_options();
    if (!$opts['enabled']) return $urls;
    $origin = '';
    if ($opts['r2_enabled'] && $opts['r2_public_base']) {
        $parts = wp_parse_url($opts['r2_public_base']);
        if (!empty($parts['scheme']) && !empty($parts['host'])) $origin = $parts['scheme'] . '://' . $parts['host'];
    } elseif ($opts['legacy_bridge']) {
        $origin = RUNNER3_LEGACY_R2_ORIGIN;
    }
    if ($origin && ($relation_type === 'preconnect' || $relation_type === 'dns-prefetch')) $urls[] = $origin;
    return array_values(array_unique($urls, SORT_REGULAR));
}
add_filter('wp_resource_hints', 'runner3_media_resource_hints', 10, 2);

function runner3_media_backfill() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('runner3_media_backfill');
    $ids = get_posts(array(
        'post_type' => 'attachment',
        'post_status' => 'inherit',
        'post_mime_type' => array('image/jpeg', 'image/png', 'image/webp'),
        'posts_per_page' => 10,
        'fields' => 'ids',
        'orderby' => 'ID',
        'order' => 'ASC',
        'meta_query' => array(array('key' => RUNNER3_MEDIA_META, 'compare' => 'NOT EXISTS')),
    ));
    $ok = 0;
    foreach ($ids as $id) if (runner3_media_process_attachment((int) $id, true)) $ok++;
    wp_safe_redirect(add_query_arg(array('page' => RUNNER3_MEDIA_PAGE, 'runner3_backfill' => $ok), admin_url('options-general.php')));
    exit;
}
add_action('admin_post_runner3_media_backfill', 'runner3_media_backfill');

function runner3_media_rollback() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('runner3_media_rollback');
    $opts = runner3_media_options();
    $opts['enabled'] = 0;
    $opts['rewrite_srcset'] = 0;
    $opts['r2_enabled'] = 0;
    $opts['legacy_bridge'] = 0;
    update_option(RUNNER3_MEDIA_OPTION, $opts, false);
    wp_safe_redirect(add_query_arg(array('page' => RUNNER3_MEDIA_PAGE, 'runner3_rollback' => 1), admin_url('options-general.php')));
    exit;
}
add_action('admin_post_runner3_media_rollback', 'runner3_media_rollback');

// ---- Current OFFSET compatibility bridge ---------------------------------
function runner3_legacy_candidate_srcset($stem) {
    $base = RUNNER3_LEGACY_R2_ORIGIN . RUNNER3_LEGACY_R2_SITE_PREFIX . RUNNER3_LEGACY_R2_VARIANT_DIR . $stem;
    return $base . '-w360.webp 360w, ' . $base . '-w480.webp 480w, ' . $base . '-w640.webp 640w';
}

function runner3_legacy_attr($tag, $name) {
    $pattern = '/\\b' . preg_quote($name, '/') . '\\s*=\\s*(["\\\'])(.*?)\\1/is';
    if (preg_match($pattern, $tag, $m)) return html_entity_decode($m[2], ENT_QUOTES | ENT_HTML5, 'UTF-8');
    return null;
}

function runner3_legacy_set_attr($tag, $name, $value) {
    $escaped = esc_attr($value);
    $pattern = '/\\s+' . preg_quote($name, '/') . '\\s*=\\s*(["\\\']).*?\\1/is';
    if (preg_match($pattern, $tag)) return preg_replace($pattern, ' ' . $name . '="' . $escaped . '"', $tag, 1) ?: $tag;
    return preg_replace('/\\s*\\/?>(\\s*)$/', ' ' . $name . '="' . $escaped . '">$1', $tag, 1) ?: $tag;
}

function runner3_legacy_optimize_html($html) {
    $opts = runner3_media_options();
    if (!$opts['enabled'] || !$opts['legacy_bridge'] || $html === '' || stripos($html, '<html') === false) return $html;
    $html = preg_replace_callback('/<img\\b[^>]*>/is', function($m) {
        $tag = $m[0];
        $src = runner3_legacy_attr($tag, 'src');
        $origin = preg_quote(RUNNER3_LEGACY_R2_ORIGIN . RUNNER3_LEGACY_R2_SITE_PREFIX, '/');
        if (!$src || !preg_match('/^' . $origin . '(offset-demo-(0[1-8]))\\.webp(?:[?#].*)?$/i', $src, $mm)) return $tag;
        $tag = runner3_legacy_set_attr($tag, 'srcset', runner3_legacy_candidate_srcset(strtolower($mm[1])));
        if (!runner3_legacy_attr($tag, 'sizes')) $tag = runner3_legacy_set_attr($tag, 'sizes', '(max-width: 800px) 92vw, 46vw');
        return $tag;
    }, $html) ?: $html;
    $hero_seen = false;
    $html = preg_replace_callback('/<link\\b[^>]*>/is', function($m) use (&$hero_seen) {
        $tag = $m[0];
        $hero = RUNNER3_LEGACY_R2_ORIGIN . RUNNER3_LEGACY_R2_SITE_PREFIX . 'offset-demo-01.webp';
        if (strtolower((string) runner3_legacy_attr($tag, 'rel')) !== 'preload' || strtolower((string) runner3_legacy_attr($tag, 'as')) !== 'image' || strtok((string) runner3_legacy_attr($tag, 'href'), '?#') !== $hero) return $tag;
        $hero_seen = true;
        $tag = runner3_legacy_set_attr($tag, 'imagesrcset', runner3_legacy_candidate_srcset('offset-demo-01'));
        return runner3_legacy_set_attr($tag, 'imagesizes', '(max-width: 767px) 80vw, 580px');
    }, $html) ?: $html;
    if (!$hero_seen && stripos($html, '</head>') !== false) {
        $hero = RUNNER3_LEGACY_R2_ORIGIN . RUNNER3_LEGACY_R2_SITE_PREFIX . 'offset-demo-01.webp';
        $preload = '<link rel="preload" as="image" href="' . esc_url($hero) . '" imagesrcset="' . esc_attr(runner3_legacy_candidate_srcset('offset-demo-01')) . '" imagesizes="(max-width: 767px) 80vw, 580px">';
        $html = preg_replace('/<\\/head>/i', $preload . "\n</head>", $html, 1) ?: $html;
    }
    return $html;
}

function runner3_legacy_start_buffer() {
    $opts = runner3_media_options();
    if (!$opts['enabled'] || !$opts['legacy_bridge'] || is_admin() || wp_doing_ajax() || is_feed() || is_robots() || (defined('REST_REQUEST') && REST_REQUEST)) return;
    if (isset($_SERVER['REQUEST_METHOD']) && $_SERVER['REQUEST_METHOD'] !== 'GET') return;
    ob_start('runner3_legacy_optimize_html');
}
add_action('template_redirect', 'runner3_legacy_start_buffer', 0);
