<?php
/**
 * Plugin Name: Runner3 Edge Cache Purge
 * Description: Purges the Runner3 Cloudflare full-page HTML cache after WordPress content changes, with signed requests, manual purge and rollback controls.
 * Version: 1.2.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) exit;

const RUNNER3_EDGE_OPTION = 'runner3_edge_cache_purge';
const RUNNER3_EDGE_STATUS_OPTION = 'runner3_edge_cache_purge_status';
const RUNNER3_EDGE_KEY_OPTION = 'runner3_edge_cache_signing_key';
const RUNNER3_EDGE_PAGE = 'runner3-edge-cache';

function runner3_edge_defaults() {
    return array('enabled' => 1, 'endpoint' => 'https://wordpress-edge-proxy.ducduy2411.workers.dev/__runner3/cache/purge');
}
function runner3_edge_options() { return wp_parse_args((array) get_option(RUNNER3_EDGE_OPTION, array()), runner3_edge_defaults()); }
function runner3_edge_sanitize($input) {
    $current = runner3_edge_options(); $input = (array) $input;
    $endpoint = isset($input['endpoint']) ? esc_url_raw(trim((string) $input['endpoint'])) : $current['endpoint'];
    if ($endpoint && stripos($endpoint, 'https://') !== 0) { add_settings_error(RUNNER3_EDGE_OPTION, 'endpoint_https', 'Edge purge endpoint must use HTTPS.'); $endpoint = $current['endpoint']; }
    return array('enabled' => empty($input['enabled']) ? 0 : 1, 'endpoint' => $endpoint);
}
function runner3_edge_register_settings() { register_setting('runner3_edge_group', RUNNER3_EDGE_OPTION, array('sanitize_callback' => 'runner3_edge_sanitize')); }
add_action('admin_init', 'runner3_edge_register_settings');

function runner3_edge_valid_pair($pair) {
    return is_array($pair) && !empty($pair['algorithm']) && !empty($pair['private']) && !empty($pair['public']) && !empty($pair['key_id']);
}
function runner3_edge_make_ed25519_pair() {
    if (!function_exists('sodium_crypto_sign_keypair') || !function_exists('sodium_crypto_sign_secretkey') || !function_exists('sodium_crypto_sign_publickey') || !function_exists('sodium_crypto_sign_detached')) return new WP_Error('sodium_unavailable');
    try {
        $kp = sodium_crypto_sign_keypair();
        $secret = sodium_crypto_sign_secretkey($kp); $public = sodium_crypto_sign_publickey($kp);
        $public_b64 = base64_encode($public);
        return array('algorithm' => 'Ed25519', 'private' => base64_encode($secret), 'public' => $public_b64, 'key_id' => hash('sha256', $public_b64), 'created_at' => gmdate('c'));
    } catch (Throwable $e) { return new WP_Error('sodium_key_generation_failed'); }
}
function runner3_edge_make_rsa_pair() {
    if (!function_exists('openssl_pkey_new') || !function_exists('openssl_pkey_export') || !function_exists('openssl_pkey_get_details') || !function_exists('openssl_sign')) return new WP_Error('openssl_unavailable');
    $resource = openssl_pkey_new(array('private_key_bits' => 2048, 'private_key_type' => OPENSSL_KEYTYPE_RSA));
    if (!$resource) return new WP_Error('key_generation_failed');
    $private = ''; if (!openssl_pkey_export($resource, $private)) return new WP_Error('private_key_export_failed');
    $details = openssl_pkey_get_details($resource); $public = is_array($details) && !empty($details['key']) ? $details['key'] : '';
    if (!$public) return new WP_Error('public_key_export_failed');
    return array('algorithm' => 'RSASSA-PKCS1-v1_5-SHA256', 'private' => $private, 'public' => $public, 'key_id' => hash('sha256', $public), 'created_at' => gmdate('c'));
}
function runner3_edge_ensure_keypair() {
    $existing = (array) get_option(RUNNER3_EDGE_KEY_OPTION, array());
    if (runner3_edge_valid_pair($existing)) return $existing;
    $pair = runner3_edge_make_ed25519_pair();
    if (is_wp_error($pair)) $pair = runner3_edge_make_rsa_pair();
    if (is_wp_error($pair)) return new WP_Error('signing_backend_unavailable', $pair->get_error_code());
    update_option(RUNNER3_EDGE_KEY_OPTION, $pair, false); return $pair;
}
function runner3_edge_activate() { runner3_edge_ensure_keypair(); }
register_activation_hook(__FILE__, 'runner3_edge_activate');

function runner3_edge_register_rest() {
    register_rest_route('runner3/v1', '/edge-key', array('methods' => 'GET', 'permission_callback' => '__return_true', 'callback' => function () {
        $pair = runner3_edge_ensure_keypair();
        if (is_wp_error($pair)) return new WP_Error('runner3_edge_key_unavailable', $pair->get_error_code(), array('status' => 503));
        return rest_ensure_response(array('algorithm' => $pair['algorithm'], 'public_key' => $pair['public'], 'key_id' => $pair['key_id']));
    }));
}
add_action('rest_api_init', 'runner3_edge_register_rest');

function runner3_edge_admin_menu() { add_options_page('Runner3 Edge Cache', 'Runner3 Edge Cache', 'manage_options', RUNNER3_EDGE_PAGE, 'runner3_edge_settings_page'); }
add_action('admin_menu', 'runner3_edge_admin_menu');
function runner3_edge_safe_status() { return wp_parse_args((array) get_option(RUNNER3_EDGE_STATUS_OPTION, array()), array('ok'=>null,'http'=>null,'at'=>'','reason'=>'','detail'=>'')); }
function runner3_edge_settings_page() {
    if (!current_user_can('manage_options')) return;
    $opts = runner3_edge_options(); $status = runner3_edge_safe_status(); $pair = runner3_edge_ensure_keypair();
    $key_id = is_wp_error($pair) ? 'UNAVAILABLE' : substr($pair['key_id'], 0, 16) . '…';
    $algorithm = is_wp_error($pair) ? $pair->get_error_code() : $pair['algorithm'];
    ?>
    <div class="wrap"><h1>Runner3 Edge Cache</h1><?php settings_errors(); ?>
    <p><strong>Status:</strong> <?php echo $opts['enabled'] ? '<span style="color:#008a20">ACTIVE</span>' : '<span style="color:#b32d2e">DISABLED / ROLLBACK</span>'; ?></p>
    <p>Published content changes automatically invalidate the Cloudflare public HTML cache. Purge requests are signed locally; the private signing key never leaves WordPress.</p>
    <form method="post" action="options.php"><?php settings_fields('runner3_edge_group'); ?>
    <table class="form-table" role="presentation">
      <tr><th scope="row">Master switch</th><td><label><input type="checkbox" name="<?php echo RUNNER3_EDGE_OPTION; ?>[enabled]" value="1" <?php checked($opts['enabled'],1); ?>> Purge edge cache automatically after public content changes</label></td></tr>
      <tr><th scope="row">Purge endpoint</th><td><input type="url" class="regular-text code" name="<?php echo RUNNER3_EDGE_OPTION; ?>[endpoint]" value="<?php echo esc_attr($opts['endpoint']); ?>" autocomplete="off"></td></tr>
      <tr><th scope="row">Signing key</th><td><code><?php echo esc_html($key_id); ?></code> · <?php echo esc_html($algorithm); ?><p class="description">Only the public key is exposed for verification. The private key is stored as a non-autoloaded WordPress option.</p></td></tr>
    </table><?php submit_button('Save Edge Cache Settings'); ?></form><hr>
    <h2>Manual purge</h2><p><a class="button button-secondary" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=runner3_edge_manual_purge'), 'runner3_edge_manual_purge')); ?>">Purge public HTML cache now</a></p>
    <p><strong>Last result:</strong> <?php if ($status['ok']===null) echo 'Not run yet'; else echo $status['ok']?'OK':'FAILED'; if ($status['http']!==null) echo ' · HTTP '.esc_html((string)$status['http']); if ($status['at']) echo ' · '.esc_html($status['at']); if ($status['reason']) echo ' · '.esc_html($status['reason']); if ($status['detail']) echo ' · '.esc_html($status['detail']); ?></p>
    <p><strong>Rollback:</strong> uncheck the master switch. This stops future purge calls without changing content, theme files or the Cloudflare Worker.</p></div>
    <?php
}
function runner3_edge_record_status($ok,$http,$reason,$detail='') { update_option(RUNNER3_EDGE_STATUS_OPTION,array('ok'=>(bool)$ok,'http'=>$http===null?null:(int)$http,'at'=>gmdate('c'),'reason'=>sanitize_text_field((string)$reason),'detail'=>sanitize_text_field(substr((string)$detail,0,240))),false); }
function runner3_edge_url_path($url) { $parts=wp_parse_url((string)$url); if(!is_array($parts)||empty($parts['path'])) return '/'; $path=$parts['path']; if(!empty($parts['query']))$path.='?'.$parts['query']; return $path; }
function runner3_edge_sign_message($pair,$message) {
    if ($pair['algorithm']==='Ed25519') {
        if (!function_exists('sodium_crypto_sign_detached')) return new WP_Error('sodium_unavailable');
        $secret=base64_decode($pair['private'],true); if($secret===false) return new WP_Error('private_key_invalid');
        try { return sodium_crypto_sign_detached($message,$secret); } catch(Throwable $e) { return new WP_Error('signature_failed'); }
    }
    if ($pair['algorithm']==='RSASSA-PKCS1-v1_5-SHA256' && function_exists('openssl_sign')) { $sig=''; return openssl_sign($message,$sig,$pair['private'],OPENSSL_ALGO_SHA256)?$sig:new WP_Error('signature_failed'); }
    return new WP_Error('signing_backend_unavailable');
}
function runner3_edge_purge($reason='wordpress-change',$urls=array(),$force=false) {
    static $sent=false; $opts=runner3_edge_options();
    if(!$force&&(!$opts['enabled']||$sent)) return false;
    if(empty($opts['endpoint'])) { runner3_edge_record_status(false,null,$reason,'endpoint_missing'); return false; }
    $pair=runner3_edge_ensure_keypair(); if(is_wp_error($pair)){runner3_edge_record_status(false,null,$reason,$pair->get_error_code());return false;}
    $sent=true; $paths=array('/'); foreach((array)$urls as $url){$path=runner3_edge_url_path($url);if($path&&!in_array($path,$paths,true))$paths[]=$path;if(count($paths)>=8)break;}
    $body=wp_json_encode(array('reason'=>sanitize_text_field((string)$reason),'urls'=>$paths),JSON_UNESCAPED_SLASHES); $timestamp=(string)time(); $signature=runner3_edge_sign_message($pair,$timestamp."\n".$body);
    if(is_wp_error($signature)){runner3_edge_record_status(false,null,$reason,$signature->get_error_code());return false;}
    $response=wp_remote_post($opts['endpoint'],array('timeout'=>12,'redirection'=>0,'sslverify'=>true,'headers'=>array('Content-Type'=>'application/json','X-Runner3-Timestamp'=>$timestamp,'X-Runner3-Signature'=>base64_encode($signature),'X-Runner3-Key-Id'=>$pair['key_id']),'body'=>$body));
    if(is_wp_error($response)){runner3_edge_record_status(false,null,$reason,$response->get_error_code());return false;}
    $http=(int)wp_remote_retrieve_response_code($response); $response_body=json_decode((string)wp_remote_retrieve_body($response),true);
    $ok=$http>=200&&$http<300&&is_array($response_body)&&!empty($response_body['ok'])&&!empty($response_body['purged'])&&!empty($response_body['cache_verified']);
    runner3_edge_record_status($ok,$http,$reason,$ok?'purged_prewarmed_cache_verified':'purge_rejected'); return $ok;
}
function runner3_edge_manual_purge(){if(!current_user_can('manage_options'))wp_die('Forbidden');check_admin_referer('runner3_edge_manual_purge');runner3_edge_purge('manual-admin',array(home_url('/')),true);wp_safe_redirect(add_query_arg(array('page'=>RUNNER3_EDGE_PAGE,'purged'=>1),admin_url('options-general.php')));exit;}
add_action('admin_post_runner3_edge_manual_purge','runner3_edge_manual_purge');
function runner3_edge_post_change($post_id,$post=null){if(wp_is_post_revision($post_id)||wp_is_post_autosave($post_id))return;$post=$post?:get_post($post_id);if(!$post||$post->post_status!=='publish')return;runner3_edge_purge('post-save',array(get_permalink($post_id),home_url('/')));}
add_action('save_post','runner3_edge_post_change',20,2);
function runner3_edge_transition($new,$old,$post){if(!$post||($new!=='publish'&&$old!=='publish'))return;runner3_edge_purge('post-status-change',array(get_permalink($post),home_url('/')));}
add_action('transition_post_status','runner3_edge_transition',20,3);
function runner3_edge_post_removed($post_id){runner3_edge_purge('post-remove',array(home_url('/')));}
add_action('trashed_post','runner3_edge_post_removed');add_action('deleted_post','runner3_edge_post_removed');add_action('untrashed_post','runner3_edge_post_removed');
function runner3_edge_global_change(){runner3_edge_purge('site-structure-change',array(home_url('/')));}
add_action('wp_update_nav_menu','runner3_edge_global_change');add_action('switch_theme','runner3_edge_global_change');add_action('customize_save_after','runner3_edge_global_change');
function runner3_edge_comment_change(){runner3_edge_purge('comment-change',array(home_url('/')));}
add_action('comment_post','runner3_edge_comment_change');add_action('edit_comment','runner3_edge_comment_change');add_action('wp_set_comment_status','runner3_edge_comment_change');
