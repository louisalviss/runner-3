<?php
/**
 * Plugin Name: Runner3 Edge Cache Purge
 * Description: Purges the Runner3 Cloudflare full-page HTML cache after WordPress content changes, with HMAC-signed requests, manual purge and rollback controls.
 * Version: 1.3.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) exit;

const RUNNER3_EDGE_OPTION = 'runner3_edge_cache_purge';
const RUNNER3_EDGE_STATUS_OPTION = 'runner3_edge_cache_purge_status';
const RUNNER3_EDGE_PAGE = 'runner3-edge-cache';

function runner3_edge_defaults() {
    return array(
        'enabled' => 1,
        'endpoint' => 'https://wordpress-edge-proxy.ducduy2411.workers.dev/__runner3/cache/purge',
        'secret' => '',
    );
}
function runner3_edge_options() { return wp_parse_args((array) get_option(RUNNER3_EDGE_OPTION, array()), runner3_edge_defaults()); }
function runner3_edge_sanitize($input) {
    $current = runner3_edge_options(); $input = (array) $input;
    $endpoint = isset($input['endpoint']) ? esc_url_raw(trim((string) $input['endpoint'])) : $current['endpoint'];
    if ($endpoint && stripos($endpoint, 'https://') !== 0) { add_settings_error(RUNNER3_EDGE_OPTION, 'endpoint_https', 'Edge purge endpoint must use HTTPS.'); $endpoint = $current['endpoint']; }
    $secret = isset($input['secret']) ? trim((string) $input['secret']) : '';
    if ($secret === '') $secret = (string) $current['secret'];
    return array('enabled' => empty($input['enabled']) ? 0 : 1, 'endpoint' => $endpoint, 'secret' => $secret);
}
function runner3_edge_register_settings() { register_setting('runner3_edge_group', RUNNER3_EDGE_OPTION, array('sanitize_callback' => 'runner3_edge_sanitize')); }
add_action('admin_init', 'runner3_edge_register_settings');

function runner3_edge_admin_menu() { add_options_page('Runner3 Edge Cache', 'Runner3 Edge Cache', 'manage_options', RUNNER3_EDGE_PAGE, 'runner3_edge_settings_page'); }
add_action('admin_menu', 'runner3_edge_admin_menu');
function runner3_edge_safe_status() { return wp_parse_args((array) get_option(RUNNER3_EDGE_STATUS_OPTION, array()), array('ok'=>null,'http'=>null,'at'=>'','reason'=>'','detail'=>'')); }
function runner3_edge_settings_page() {
    if (!current_user_can('manage_options')) return;
    $opts = runner3_edge_options(); $status = runner3_edge_safe_status();
    ?>
    <div class="wrap"><h1>Runner3 Edge Cache</h1><?php settings_errors(); ?>
    <p><strong>Status:</strong> <?php echo $opts['enabled'] ? '<span style="color:#008a20">ACTIVE</span>' : '<span style="color:#b32d2e">DISABLED / ROLLBACK</span>'; ?></p>
    <p>Published content changes automatically invalidate the Cloudflare public HTML cache. Purge requests use a timestamped HMAC signature; the shared secret is never displayed or sent in the request.</p>
    <form method="post" action="options.php"><?php settings_fields('runner3_edge_group'); ?>
    <table class="form-table" role="presentation">
      <tr><th scope="row">Master switch</th><td><label><input type="checkbox" name="<?php echo RUNNER3_EDGE_OPTION; ?>[enabled]" value="1" <?php checked($opts['enabled'],1); ?>> Purge edge cache automatically after public content changes</label></td></tr>
      <tr><th scope="row">Purge endpoint</th><td><input type="url" class="regular-text code" name="<?php echo RUNNER3_EDGE_OPTION; ?>[endpoint]" value="<?php echo esc_attr($opts['endpoint']); ?>" autocomplete="off"></td></tr>
      <tr><th scope="row">Authentication</th><td><input type="password" class="regular-text code" name="<?php echo RUNNER3_EDGE_OPTION; ?>[secret]" value="" autocomplete="new-password" placeholder="<?php echo $opts['secret'] ? 'Configured — leave blank to keep' : 'Not configured'; ?>"><p class="description">A random shared secret is provisioned by the deployment workflow and stored as a non-autoloaded WordPress option plus a Cloudflare Worker secret.</p></td></tr>
    </table><?php submit_button('Save Edge Cache Settings'); ?></form><hr>
    <h2>Manual purge</h2><p><a class="button button-secondary" href="<?php echo esc_url(wp_nonce_url(admin_url('admin-post.php?action=runner3_edge_manual_purge'), 'runner3_edge_manual_purge')); ?>">Purge public HTML cache now</a></p>
    <p><strong>Last result:</strong> <?php if ($status['ok']===null) echo 'Not run yet'; else echo $status['ok']?'OK':'FAILED'; if ($status['http']!==null) echo ' · HTTP '.esc_html((string)$status['http']); if ($status['at']) echo ' · '.esc_html($status['at']); if ($status['reason']) echo ' · '.esc_html($status['reason']); if ($status['detail']) echo ' · '.esc_html($status['detail']); ?></p>
    <p><strong>Rollback:</strong> uncheck the master switch. This stops future purge calls without changing content, theme files or the Cloudflare Worker.</p></div>
    <?php
}
function runner3_edge_record_status($ok,$http,$reason,$detail='') { update_option(RUNNER3_EDGE_STATUS_OPTION,array('ok'=>(bool)$ok,'http'=>$http===null?null:(int)$http,'at'=>gmdate('c'),'reason'=>sanitize_text_field((string)$reason),'detail'=>sanitize_text_field(substr((string)$detail,0,240))),false); }
function runner3_edge_url_path($url) { $parts=wp_parse_url((string)$url); if(!is_array($parts)||empty($parts['path'])) return '/'; $path=$parts['path']; if(!empty($parts['query']))$path.='?'.$parts['query']; return $path; }
function runner3_edge_purge($reason='wordpress-change',$urls=array(),$force=false) {
    static $sent=false; $opts=runner3_edge_options();
    if(!$force&&(!$opts['enabled']||$sent)) return false;
    if(empty($opts['endpoint'])||empty($opts['secret'])) { runner3_edge_record_status(false,null,$reason,'endpoint_or_auth_missing'); return false; }
    if(!function_exists('hash_hmac')) { runner3_edge_record_status(false,null,$reason,'hmac_unavailable'); return false; }
    $sent=true; $paths=array('/'); foreach((array)$urls as $url){$path=runner3_edge_url_path($url);if($path&&!in_array($path,$paths,true))$paths[]=$path;if(count($paths)>=8)break;}
    $body=wp_json_encode(array('reason'=>sanitize_text_field((string)$reason),'urls'=>$paths),JSON_UNESCAPED_SLASHES); $timestamp=(string)time();
    $signature=base64_encode(hash_hmac('sha256',$timestamp."\n".$body,(string)$opts['secret'],true));
    $response=wp_remote_post($opts['endpoint'],array('timeout'=>12,'redirection'=>0,'sslverify'=>true,'headers'=>array('Content-Type'=>'application/json','X-Runner3-Timestamp'=>$timestamp,'X-Runner3-Signature'=>$signature),'body'=>$body));
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
