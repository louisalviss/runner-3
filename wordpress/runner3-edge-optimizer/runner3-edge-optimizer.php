<?php
/**
 * Plugin Name: Runner3 Edge Optimizer
 * Description: Debounced authenticated WordPress change events for Runner3 edge automation.
 * Version: 0.2.0
 * Author: Runner3
 */
if (!defined('ABSPATH')) exit;

final class Runner3_Edge_Optimizer {
    const VERSION='0.2.0'; const CRON='runner3_edge_optimizer_flush'; const PENDING='runner3_edge_optimizer_pending';
    const ENDPOINT='https://runner3wp.pntr.dev/__runner3/automation/events';
    public static function boot(){
        add_action('save_post',[__CLASS__,'save'],20,3); add_action('before_delete_post',[__CLASS__,'delete'],10,2);
        add_action('transition_post_status',[__CLASS__,'status'],20,3); add_action('wp_update_nav_menu',[__CLASS__,'global'],20);
        add_action('customize_save_after',[__CLASS__,'global'],20); add_action('switch_theme',[__CLASS__,'global'],20);
        add_action('edited_term',[__CLASS__,'global'],20); add_action('delete_term',[__CLASS__,'global'],20);
        add_action('add_attachment',[__CLASS__,'attachment'],20); add_action('edit_attachment',[__CLASS__,'attachment'],20);
        add_action('delete_attachment',[__CLASS__,'attachment'],20); add_action(self::CRON,[__CLASS__,'flush']);
    }
    private static function endpoint(){return defined('RUNNER3_EDGE_AUTOMATION_ENDPOINT')&&RUNNER3_EDGE_AUTOMATION_ENDPOINT?esc_url_raw(RUNNER3_EDGE_AUTOMATION_ENDPOINT):self::ENDPOINT;}
    private static function secret(){
        if(defined('RUNNER3_EDGE_AUTOMATION_SECRET')&&RUNNER3_EDGE_AUTOMATION_SECRET)return(string)RUNNER3_EDGE_AUTOMATION_SECRET;
        $legacy=get_option('runner3_edge_cache_purge',[]); if(is_array($legacy)&&!empty($legacy['secret'])&&is_string($legacy['secret']))return $legacy['secret'];
        $own=get_option('runner3_edge_optimizer_secret',''); return is_string($own)?$own:'';
    }
    private static function path($url){if(!$url||!is_string($url))return null;$p=wp_parse_url($url);if(!$p)return null;$x=$p['path']??'/';if(!empty($p['query']))$x.='?'.$p['query'];return substr($x,0,600);}
    private static function urls($id){$u=['/'];$link=get_permalink($id);if($link)$u[]=self::path($link);$p=get_post($id);if($p){$a=get_post_type_archive_link($p->post_type);if($a)$u[]=self::path($a);foreach(get_object_taxonomies($p->post_type)as$t){$terms=wp_get_post_terms($id,$t);if(is_wp_error($terms))continue;foreach(array_slice($terms,0,12)as$term){$l=get_term_link($term);if(!is_wp_error($l))$u[]=self::path($l);}}}return array_values(array_unique(array_filter($u)));}
    private static function media($id,$role='featured',$post_id=null){$aid=$role==='featured'?get_post_thumbnail_id($id):$id;if(!$aid)return[];$url=wp_get_attachment_url($aid);if(!$url)return[];$m=wp_get_attachment_metadata($aid);return[['url'=>$url,'attachmentId'=>(int)$aid,'postId'=>$post_id===null?($role==='featured'?(int)$id:null):(int)$post_id,'role'=>$role,'width'=>is_array($m)&&isset($m['width'])?(int)$m['width']:null,'height'=>is_array($m)&&isset($m['height'])?(int)$m['height']:null,'mime'=>get_post_mime_type($aid)?:null]];}
    private static function enqueue($reason,$urls=['/'],$global=false,$media=[]){$q=get_option(self::PENDING,[]);if(!is_array($q))$q=[];$q['reasons']=array_values(array_unique(array_filter(array_merge($q['reasons']??[],[(string)$reason]))));$q['urls']=array_values(array_unique(array_filter(array_merge($q['urls']??[],$urls))));$q['global']=!empty($q['global'])||$global;$q['media']=array_slice(array_merge($q['media']??[],$media),-16);$q['updatedAt']=time();update_option(self::PENDING,$q,false);if(!wp_next_scheduled(self::CRON))wp_schedule_single_event(time()+20,self::CRON);}
    public static function save($id,$post,$update){if(wp_is_post_revision($id)||wp_is_post_autosave($id)||!$post||in_array($post->post_status,['auto-draft','inherit'],true))return;self::enqueue($update?'save_post:update':'save_post:create',self::urls($id),false,self::media($id));}
    public static function delete($id,$post=null){self::enqueue('delete_post',self::urls($id),false,self::media($id));}
    public static function status($new,$old,$post){if(!$post||$new===$old||wp_is_post_revision($post->ID))return;self::enqueue('status:'.$old.'->'.$new,self::urls($post->ID),false,self::media($post->ID));}
    public static function global(){self::enqueue('global_change',['/'],true,[]);}
    public static function attachment($id){self::enqueue('attachment_change',['/'],false,self::media($id,'attachment'));}
    public static function flush(){
        $q=get_option(self::PENDING,[]);if(!is_array($q)||empty($q['reasons']))return;$secret=self::secret();if($secret===''){error_log('Runner3 Edge Optimizer: HMAC secret unavailable');wp_schedule_single_event(time()+300,self::CRON);return;}
        $payload=['op'=>'enqueue','source'=>'runner3-edge-optimizer/'.self::VERSION,'reason'=>$q['reasons'][0],'reasons'=>array_slice($q['reasons'],0,16),'urls'=>array_slice(!empty($q['urls'])?$q['urls']:['/'],0,40),'global'=>!empty($q['global']),'media'=>array_slice($q['media']??[],0,16)];
        $body=wp_json_encode($payload,JSON_UNESCAPED_SLASHES);$ts=(string)time();$sig=base64_encode(hash_hmac('sha256',$ts."\n".$body,$secret,true));
        $r=wp_remote_post(self::endpoint(),['timeout'=>8,'redirection'=>0,'headers'=>['Content-Type'=>'application/json','X-Runner3-Timestamp'=>$ts,'X-Runner3-Signature'=>$sig],'body'=>$body,'data_format'=>'body']);
        if(!is_wp_error($r)){ $code=(int)wp_remote_retrieve_response_code($r);if($code>=200&&$code<300){delete_option(self::PENDING);return;}error_log('Runner3 Edge Optimizer enqueue HTTP '.$code);}else error_log('Runner3 Edge Optimizer enqueue failed: '.$r->get_error_message());
        wp_schedule_single_event(time()+60,self::CRON);
    }
}
Runner3_Edge_Optimizer::boot();
