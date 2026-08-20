<?php
/**
 * Plugin Name: Runner3 Edge Optimizer
 * Description: Debounced authenticated WordPress change events for Runner3 edge automation.
 * Version: 0.3.0
 * Author: Runner3
 */
if (!defined('ABSPATH')) exit;

final class Runner3_Edge_Optimizer {
    const VERSION='0.3.0';
    const CRON='runner3_edge_optimizer_flush';
    const PENDING='runner3_edge_optimizer_pending';
    const ENDPOINT_OPTION='runner3_edge_optimizer_endpoint';
    const SECRET_OPTION='runner3_edge_optimizer_secret';
    const DEFAULT_ENDPOINT='https://runner3-wp-control.ducduy2411.workers.dev/v1/events';

    public static function boot(){
        add_action('save_post',[__CLASS__,'save'],20,3); add_action('before_delete_post',[__CLASS__,'delete'],10,2);
        add_action('transition_post_status',[__CLASS__,'status'],20,3); add_action('wp_update_nav_menu',[__CLASS__,'global'],20);
        add_action('customize_save_after',[__CLASS__,'global'],20); add_action('switch_theme',[__CLASS__,'global'],20);
        add_action('edited_term',[__CLASS__,'global'],20); add_action('delete_term',[__CLASS__,'global'],20);
        add_action('add_attachment',[__CLASS__,'attachment'],20); add_action('edit_attachment',[__CLASS__,'attachment'],20);
        add_action('delete_attachment',[__CLASS__,'attachment'],20); add_action(self::CRON,[__CLASS__,'flush']);
        add_action('admin_menu',[__CLASS__,'admin_menu']); add_action('admin_init',[__CLASS__,'admin_init']);
        add_action('admin_post_runner3_edge_optimizer_test',[__CLASS__,'test_connection']);
    }

    public static function admin_menu(){add_options_page('Runner3 Edge Optimizer','Runner3 Edge Optimizer','manage_options','runner3-edge-optimizer',[__CLASS__,'settings_page']);}
    public static function admin_init(){
        register_setting('runner3_edge_optimizer',self::ENDPOINT_OPTION,['type'=>'string','sanitize_callback'=>[__CLASS__,'sanitize_endpoint'],'default'=>self::DEFAULT_ENDPOINT]);
        register_setting('runner3_edge_optimizer',self::SECRET_OPTION,['type'=>'string','sanitize_callback'=>[__CLASS__,'sanitize_secret'],'default'=>'']);
    }
    public static function sanitize_endpoint($value){$v=esc_url_raw((string)$value);return strpos($v,'https://')===0?$v:self::DEFAULT_ENDPOINT;}
    public static function sanitize_secret($value){$v=trim((string)$value);if($v==='')return (string)get_option(self::SECRET_OPTION,'');return substr($v,0,256);}
    public static function settings_page(){
        if(!current_user_can('manage_options'))return;
        $endpoint=esc_attr(self::endpoint());$configured=self::secret()!=='';
        echo '<div class="wrap"><h1>Runner3 Edge Optimizer</h1><p>Event-only control plane. Frontend serving path is untouched.</p>';
        if(isset($_GET['runner3_test']))echo '<div class="notice notice-'.($_GET['runner3_test']==='ok'?'success':'error').' is-dismissible"><p>Connection test: '.esc_html($_GET['runner3_test']).'</p></div>';
        echo '<form method="post" action="options.php">';settings_fields('runner3_edge_optimizer');
        echo '<table class="form-table"><tr><th>Control endpoint</th><td><input id="runner3-edge-endpoint" name="'.esc_attr(self::ENDPOINT_OPTION).'" type="url" class="regular-text" value="'.$endpoint.'" required></td></tr>';
        echo '<tr><th>Automation secret</th><td><input id="runner3-edge-secret" name="'.esc_attr(self::SECRET_OPTION).'" type="password" class="regular-text" value="" placeholder="'.($configured?'Configured':'Not configured').'"><p class="description">Leave blank to keep the stored secret.</p></td></tr></table>';
        submit_button('Save Settings');echo '</form>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'" style="margin-top:16px"><input type="hidden" name="action" value="runner3_edge_optimizer_test">';wp_nonce_field('runner3_edge_optimizer_test');submit_button('Send Test Event','secondary');echo '</form></div>';
    }

    private static function endpoint(){if(defined('RUNNER3_EDGE_AUTOMATION_ENDPOINT')&&RUNNER3_EDGE_AUTOMATION_ENDPOINT)return esc_url_raw(RUNNER3_EDGE_AUTOMATION_ENDPOINT);$v=get_option(self::ENDPOINT_OPTION,self::DEFAULT_ENDPOINT);return esc_url_raw($v?:self::DEFAULT_ENDPOINT);}
    private static function secret(){
        if(defined('RUNNER3_EDGE_AUTOMATION_SECRET')&&RUNNER3_EDGE_AUTOMATION_SECRET)return(string)RUNNER3_EDGE_AUTOMATION_SECRET;
        $own=get_option(self::SECRET_OPTION,'');if(is_string($own)&&$own!=='')return $own;
        $legacy=get_option('runner3_edge_cache_purge',[]);if(is_array($legacy)&&!empty($legacy['secret'])&&is_string($legacy['secret']))return $legacy['secret'];
        return '';
    }
    private static function path($url){if(!$url||!is_string($url))return null;$p=wp_parse_url($url);if(!$p)return null;$x=$p['path']??'/';if(!empty($p['query']))$x.='?'.$p['query'];return substr($x,0,600);}
    private static function urls($id){$u=['/'];$link=get_permalink($id);if($link)$u[]=self::path($link);$p=get_post($id);if($p){$a=get_post_type_archive_link($p->post_type);if($a)$u[]=self::path($a);foreach(get_object_taxonomies($p->post_type)as$t){$terms=wp_get_post_terms($id,$t);if(is_wp_error($terms))continue;foreach(array_slice($terms,0,12)as$term){$l=get_term_link($term);if(!is_wp_error($l))$u[]=self::path($l);}}}return array_values(array_unique(array_filter($u)));}
    private static function media($id,$role='featured',$post_id=null){$aid=$role==='featured'?get_post_thumbnail_id($id):$id;if(!$aid)return[];$url=wp_get_attachment_url($aid);if(!$url)return[];$m=wp_get_attachment_metadata($aid);return[['url'=>$url,'attachmentId'=>(int)$aid,'postId'=>$post_id===null?($role==='featured'?(int)$id:null):(int)$post_id,'role'=>$role,'width'=>is_array($m)&&isset($m['width'])?(int)$m['width']:null,'height'=>is_array($m)&&isset($m['height'])?(int)$m['height']:null,'mime'=>get_post_mime_type($aid)?:null]];}
    private static function enqueue($reason,$urls=['/'],$global=false,$media=[]){$q=get_option(self::PENDING,[]);if(!is_array($q))$q=[];$q['reasons']=array_values(array_unique(array_filter(array_merge($q['reasons']??[],[(string)$reason]))));$q['urls']=array_values(array_unique(array_filter(array_merge($q['urls']??[],$urls))));$q['global']=!empty($q['global'])||$global;$q['media']=array_slice(array_merge($q['media']??[],$media),-16);$q['updatedAt']=time();update_option(self::PENDING,$q,false);if(!wp_next_scheduled(self::CRON))wp_schedule_single_event(time()+20,self::CRON);}
    private static function send_pending(){
        $q=get_option(self::PENDING,[]);if(!is_array($q)||empty($q['reasons']))return true;$secret=self::secret();if($secret==='')return false;
        $payload=['op'=>'enqueue','source'=>'runner3-edge-optimizer/'.self::VERSION,'reason'=>$q['reasons'][0],'reasons'=>array_slice($q['reasons'],0,16),'urls'=>array_slice(!empty($q['urls'])?$q['urls']:['/'],0,40),'global'=>!empty($q['global']),'media'=>array_slice($q['media']??[],0,16)];
        $body=wp_json_encode($payload,JSON_UNESCAPED_SLASHES);$ts=(string)time();$sig=base64_encode(hash_hmac('sha256',$ts."\n".$body,$secret,true));
        $r=wp_remote_post(self::endpoint(),['timeout'=>8,'redirection'=>0,'headers'=>['Content-Type'=>'application/json','X-Runner3-Timestamp'=>$ts,'X-Runner3-Signature'=>$sig],'body'=>$body,'data_format'=>'body']);
        if(is_wp_error($r)){error_log('Runner3 Edge Optimizer enqueue failed: '.$r->get_error_message());return false;}
        $code=(int)wp_remote_retrieve_response_code($r);if($code>=200&&$code<300){delete_option(self::PENDING);return true;}error_log('Runner3 Edge Optimizer enqueue HTTP '.$code);return false;
    }
    public static function save($id,$post,$update){if(wp_is_post_revision($id)||wp_is_post_autosave($id)||!$post||in_array($post->post_status,['auto-draft','inherit'],true))return;self::enqueue($update?'save_post:update':'save_post:create',self::urls($id),false,self::media($id));}
    public static function delete($id,$post=null){self::enqueue('delete_post',self::urls($id),false,self::media($id));}
    public static function status($new,$old,$post){if(!$post||$new===$old||wp_is_post_revision($post->ID))return;self::enqueue('status:'.$old.'->'.$new,self::urls($post->ID),false,self::media($post->ID));}
    public static function global(){self::enqueue('global_change',['/'],true,[]);}
    public static function attachment($id){self::enqueue('attachment_change',['/'],false,self::media($id,'attachment'));}
    public static function flush(){if(!self::send_pending())wp_schedule_single_event(time()+60,self::CRON);}
    public static function test_connection(){if(!current_user_can('manage_options'))wp_die('Forbidden',403);check_admin_referer('runner3_edge_optimizer_test');self::enqueue('manual_test',['/'],false,[]);$ok=self::send_pending();wp_safe_redirect(add_query_arg('runner3_test',$ok?'ok':'failed',admin_url('options-general.php?page=runner3-edge-optimizer')));exit;}
}
Runner3_Edge_Optimizer::boot();
