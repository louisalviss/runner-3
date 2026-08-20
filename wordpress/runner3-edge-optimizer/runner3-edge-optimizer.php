<?php
/**
 * Plugin Name: Runner3 Edge Optimizer
 * Description: Emits debounced, authenticated WordPress change events for Runner3 edge snapshot/image automation.
 * Version: 0.1.0
 * Author: Runner3
 */

if (!defined('ABSPATH')) exit;

final class Runner3_Edge_Optimizer {
    const VERSION = '0.1.0';
    const CRON_HOOK = 'runner3_edge_optimizer_flush';
    const QUEUE_OPTION = 'runner3_edge_optimizer_pending';
    const ENDPOINT_OPTION = 'runner3_edge_optimizer_endpoint';
    const SECRET_OPTION = 'runner3_edge_optimizer_secret';
    const DEFAULT_ENDPOINT = 'https://runner3wp.pntr.dev/__runner3/automation/events';

    public static function boot() {
        add_action('save_post', [__CLASS__, 'on_save_post'], 20, 3);
        add_action('before_delete_post', [__CLASS__, 'on_delete_post'], 10, 2);
        add_action('transition_post_status', [__CLASS__, 'on_transition'], 20, 3);
        add_action('wp_update_nav_menu', [__CLASS__, 'on_global_change'], 20, 1);
        add_action('customize_save_after', [__CLASS__, 'on_global_change'], 20, 1);
        add_action('switch_theme', [__CLASS__, 'on_global_change'], 20, 3);
        add_action('edited_term', [__CLASS__, 'on_term_change'], 20, 3);
        add_action('delete_term', [__CLASS__, 'on_term_change'], 20, 5);
        add_action('add_attachment', [__CLASS__, 'on_attachment'], 20, 1);
        add_action('edit_attachment', [__CLASS__, 'on_attachment'], 20, 1);
        add_action('delete_attachment', [__CLASS__, 'on_attachment'], 20, 1);
        add_action(self::CRON_HOOK, [__CLASS__, 'flush']);
    }

    private static function endpoint() {
        if (defined('RUNNER3_EDGE_AUTOMATION_ENDPOINT') && RUNNER3_EDGE_AUTOMATION_ENDPOINT) {
            return esc_url_raw(RUNNER3_EDGE_AUTOMATION_ENDPOINT);
        }
        $value = get_option(self::ENDPOINT_OPTION, self::DEFAULT_ENDPOINT);
        return esc_url_raw($value ?: self::DEFAULT_ENDPOINT);
    }

    private static function secret() {
        if (defined('RUNNER3_EDGE_AUTOMATION_SECRET') && RUNNER3_EDGE_AUTOMATION_SECRET) {
            return (string) RUNNER3_EDGE_AUTOMATION_SECRET;
        }
        // Reuse an existing Runner3 edge secret option when present, but never
        // write a secret into plugin source or expose it in public responses.
        foreach ([self::SECRET_OPTION, 'runner3_edge_cache_purge_secret', 'runner3_cache_purge_secret'] as $key) {
            $value = get_option($key, '');
            if (is_string($value) && $value !== '') return $value;
        }
        return '';
    }

    private static function normalize_url($url) {
        if (!$url || !is_string($url)) return null;
        $parts = wp_parse_url($url);
        if (!$parts || empty($parts['path'])) return '/';
        $path = $parts['path'];
        if (!empty($parts['query'])) $path .= '?' . $parts['query'];
        return substr($path, 0, 600);
    }

    private static function post_urls($post_id) {
        $urls = ['/'];
        $permalink = get_permalink($post_id);
        if ($permalink) $urls[] = self::normalize_url($permalink);
        $post = get_post($post_id);
        if ($post) {
            $archive = get_post_type_archive_link($post->post_type);
            if ($archive) $urls[] = self::normalize_url($archive);
            $taxonomies = get_object_taxonomies($post->post_type);
            foreach ($taxonomies as $taxonomy) {
                $terms = wp_get_post_terms($post_id, $taxonomy);
                if (is_wp_error($terms)) continue;
                foreach (array_slice($terms, 0, 12) as $term) {
                    $link = get_term_link($term);
                    if (!is_wp_error($link)) $urls[] = self::normalize_url($link);
                }
            }
        }
        return array_values(array_unique(array_filter($urls)));
    }

    private static function featured_media($post_id) {
        $attachment_id = get_post_thumbnail_id($post_id);
        if (!$attachment_id) return [];
        $url = wp_get_attachment_url($attachment_id);
        if (!$url) return [];
        $meta = wp_get_attachment_metadata($attachment_id);
        $mime = get_post_mime_type($attachment_id);
        return [[
            'url' => $url,
            'attachmentId' => (int) $attachment_id,
            'postId' => (int) $post_id,
            'role' => 'featured',
            'width' => is_array($meta) && isset($meta['width']) ? (int) $meta['width'] : null,
            'height' => is_array($meta) && isset($meta['height']) ? (int) $meta['height'] : null,
            'mime' => $mime ?: null,
        ]];
    }

    private static function enqueue($reason, $urls = ['/'], $global = false, $media = []) {
        $pending = get_option(self::QUEUE_OPTION, []);
        if (!is_array($pending)) $pending = [];
        $pending['reasons'] = array_values(array_unique(array_filter(array_merge(
            isset($pending['reasons']) && is_array($pending['reasons']) ? $pending['reasons'] : [],
            [(string) $reason]
        ))));
        $pending['urls'] = array_values(array_unique(array_filter(array_merge(
            isset($pending['urls']) && is_array($pending['urls']) ? $pending['urls'] : [],
            $urls
        ))));
        $pending['global'] = !empty($pending['global']) || $global;
        $pending['media'] = array_slice(array_merge(
            isset($pending['media']) && is_array($pending['media']) ? $pending['media'] : [],
            is_array($media) ? $media : []
        ), -16);
        $pending['updatedAt'] = time();
        update_option(self::QUEUE_OPTION, $pending, false);
        if (!wp_next_scheduled(self::CRON_HOOK)) {
            wp_schedule_single_event(time() + 20, self::CRON_HOOK);
        }
    }

    public static function on_save_post($post_id, $post, $update) {
        if (wp_is_post_revision($post_id) || wp_is_post_autosave($post_id)) return;
        if (!$post || in_array($post->post_status, ['auto-draft', 'inherit'], true)) return;
        self::enqueue($update ? 'save_post:update' : 'save_post:create', self::post_urls($post_id), false, self::featured_media($post_id));
    }

    public static function on_delete_post($post_id, $post = null) {
        self::enqueue('delete_post', self::post_urls($post_id), false, self::featured_media($post_id));
    }

    public static function on_transition($new_status, $old_status, $post) {
        if (!$post || $new_status === $old_status || wp_is_post_revision($post->ID)) return;
        self::enqueue('status:' . $old_status . '->' . $new_status, self::post_urls($post->ID), false, self::featured_media($post->ID));
    }

    public static function on_global_change() {
        self::enqueue('global_change', ['/'], true, []);
    }

    public static function on_term_change() {
        self::enqueue('taxonomy_change', ['/'], true, []);
    }

    public static function on_attachment($attachment_id) {
        $url = wp_get_attachment_url($attachment_id);
        $meta = wp_get_attachment_metadata($attachment_id);
        $mime = get_post_mime_type($attachment_id);
        $media = $url ? [[
            'url' => $url,
            'attachmentId' => (int) $attachment_id,
            'postId' => null,
            'role' => 'attachment',
            'width' => is_array($meta) && isset($meta['width']) ? (int) $meta['width'] : null,
            'height' => is_array($meta) && isset($meta['height']) ? (int) $meta['height'] : null,
            'mime' => $mime ?: null,
        ]] : [];
        self::enqueue('attachment_change', ['/'], false, $media);
    }

    public static function flush() {
        $pending = get_option(self::QUEUE_OPTION, []);
        if (!is_array($pending) || empty($pending['reasons'])) return;
        $secret = self::secret();
        if ($secret === '') {
            error_log('Runner3 Edge Optimizer: automation secret is not configured');
            return;
        }
        $payload = [
            'op' => 'enqueue',
            'source' => 'runner3-edge-optimizer/' . self::VERSION,
            'reasons' => array_slice($pending['reasons'], 0, 16),
            'reason' => $pending['reasons'][0],
            'urls' => array_slice(!empty($pending['urls']) ? $pending['urls'] : ['/'], 0, 40),
            'global' => !empty($pending['global']),
            'media' => array_slice(!empty($pending['media']) ? $pending['media'] : [], 0, 16),
        ];
        $body = wp_json_encode($payload, JSON_UNESCAPED_SLASHES);
        $timestamp = (string) time();
        $signature = base64_encode(hash_hmac('sha256', $timestamp . "\n" . $body, $secret, true));
        $response = wp_remote_post(self::endpoint(), [
            'timeout' => 8,
            'redirection' => 0,
            'headers' => [
                'Content-Type' => 'application/json',
                'X-Runner3-Timestamp' => $timestamp,
                'X-Runner3-Signature' => $signature,
            ],
            'body' => $body,
            'data_format' => 'body',
        ]);
        if (is_wp_error($response)) {
            error_log('Runner3 Edge Optimizer enqueue failed: ' . $response->get_error_message());
            wp_schedule_single_event(time() + 60, self::CRON_HOOK);
            return;
        }
        $code = (int) wp_remote_retrieve_response_code($response);
        if ($code >= 200 && $code < 300) {
            delete_option(self::QUEUE_OPTION);
            return;
        }
        error_log('Runner3 Edge Optimizer enqueue HTTP ' . $code);
        wp_schedule_single_event(time() + 60, self::CRON_HOOK);
    }
}

Runner3_Edge_Optimizer::boot();
