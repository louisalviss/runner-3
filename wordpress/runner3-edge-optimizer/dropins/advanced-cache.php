<?php
/* RUNNER3_SPEED_DROPIN v1.0.0 */
if (!defined('ABSPATH')) return;
$runner3_dir=__DIR__.'/cache/runner3-speed';$runner3_flag=$runner3_dir.'/enabled.flag';if(!is_file($runner3_flag))return;
$runner3_method=strtoupper((string)($_SERVER['REQUEST_METHOD']??'GET'));if($runner3_method!=='GET'&&$runner3_method!=='HEAD')return;if(!empty($_SERVER['QUERY_STRING']))return;
$runner3_uri=(string)($_SERVER['REQUEST_URI']??'/');$runner3_path=parse_url($runner3_uri,PHP_URL_PATH)?:'/';
if(preg_match('#^/(?:wp-admin(?:/|$)|wp-login\.php(?:/|$)|wp-json(?:/|$)|xmlrpc\.php$|wp-cron\.php$|cart(?:/|$)|checkout(?:/|$)|my-account(?:/|$)|wc-api(?:/|$))#i',$runner3_path))return;
foreach(array_keys($_COOKIE??[])as $runner3_cookie)if(preg_match('/^(wordpress_logged_in_|wordpress_sec_|wp-postpass_|woocommerce_items_in_cart$|woocommerce_cart_hash$|wp_woocommerce_session_|comment_author_)/i',(string)$runner3_cookie))return;
$runner3_host=strtolower((string)($_SERVER['HTTP_HOST']??''));if($runner3_host==='')return;$runner3_file=$runner3_dir.'/pages/'.hash('sha256',$runner3_host."\n".$runner3_path).'.html';
if(!is_file($runner3_file)){if(!headers_sent())header('X-Runner3-Speed: MISS');return;}
$runner3_mtime=@filemtime($runner3_file);if(!$runner3_mtime||(time()-$runner3_mtime)>3600){@unlink($runner3_file);if(!headers_sent())header('X-Runner3-Speed: MISS');return;}
$runner3_size=@filesize($runner3_file);if(!headers_sent()){header('Content-Type: text/html; charset=UTF-8');header('Cache-Control: public, max-age=60, stale-while-revalidate=30');header('X-Runner3-Speed: HIT');header('X-Runner3-Speed-Version: 1.0.0');if($runner3_size!==false)header('Content-Length: '.$runner3_size);}if($runner3_method==='HEAD')exit;readfile($runner3_file);exit;
