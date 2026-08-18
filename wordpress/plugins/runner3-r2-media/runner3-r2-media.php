<?php
/**
 * Plugin Name: Runner3 R2 Media
 * Description: Keeps WordPress attachment IDs while serving offloaded media from Cloudflare R2.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

function r3_r2_url($attachment_id) {
    return (string) get_post_meta((int) $attachment_id, '_r3_r2_url', true);
}

add_filter('wp_get_attachment_url', function($url, $post_id) {
    $remote = r3_r2_url($post_id);
    return $remote ?: $url;
}, 20, 2);

add_filter('image_downsize', function($downsize, $id, $size) {
    $remote = r3_r2_url($id);
    if (!$remote) return $downsize;
    $width = (int) get_post_meta($id, '_r3_r2_width', true);
    $height = (int) get_post_meta($id, '_r3_r2_height', true);
    if (!$width || !$height) {
        $meta = wp_get_attachment_metadata($id);
        $width = isset($meta['width']) ? (int) $meta['width'] : 0;
        $height = isset($meta['height']) ? (int) $meta['height'] : 0;
    }
    return array($remote, $width, $height, true);
}, 20, 3);

add_filter('wp_calculate_image_srcset', function($sources, $size_array, $image_src, $image_meta, $attachment_id) {
    return r3_r2_url($attachment_id) ? false : $sources;
}, 20, 5);

// Future Runner3 uploads are pre-resized/optimized before they reach WordPress.
add_filter('big_image_size_threshold', '__return_false');
add_filter('intermediate_image_sizes_advanced', function($sizes) {
    if (defined('RUNNER3_R2_IMPORT') && RUNNER3_R2_IMPORT) return array();
    return $sizes;
});

function r3_r2_prune_local_files($id) {
    $file = get_attached_file($id);
    $meta = wp_get_attachment_metadata($id);
    $deleted = array();
    $candidates = array();

    if ($file) $candidates[] = $file;
    if ($file && is_array($meta) && !empty($meta['sizes'])) {
        $dir = dirname($file);
        foreach ($meta['sizes'] as $size) {
            if (!empty($size['file'])) $candidates[] = $dir . DIRECTORY_SEPARATOR . $size['file'];
        }
    }
    if ($file && is_array($meta) && !empty($meta['original_image'])) {
        $candidates[] = dirname($file) . DIRECTORY_SEPARATOR . $meta['original_image'];
    }

    foreach (array_unique($candidates) as $candidate) {
        if ($candidate && file_exists($candidate) && wp_delete_file($candidate)) $deleted[] = basename($candidate);
    }

    if (is_array($meta)) {
        $meta['sizes'] = array();
        unset($meta['original_image']);
        wp_update_attachment_metadata($id, $meta);
    }
    return $deleted;
}

add_action('rest_api_init', function() {
    register_rest_route('runner3/v1', '/offload/(?P<id>\d+)', array(
        'methods' => 'POST',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function(WP_REST_Request $request) {
            $id = (int) $request['id'];
            if (get_post_type($id) !== 'attachment') return new WP_Error('not_attachment', 'Attachment not found', array('status' => 404));

            $remote = esc_url_raw((string) $request->get_param('remote_url'));
            $width = max(1, (int) $request->get_param('width'));
            $height = max(1, (int) $request->get_param('height'));
            $prune = rest_sanitize_boolean($request->get_param('prune'));
            if (!$remote || !preg_match('#^https://#i', $remote)) return new WP_Error('bad_remote_url', 'HTTPS remote URL required', array('status' => 400));

            $head = wp_remote_head($remote, array('timeout' => 15, 'redirection' => 3));
            if (is_wp_error($head)) return new WP_Error('remote_unreachable', $head->get_error_message(), array('status' => 502));
            $code = (int) wp_remote_retrieve_response_code($head);
            if ($code < 200 || $code >= 300) return new WP_Error('remote_unreachable', 'Remote media HEAD failed: '.$code, array('status' => 502));

            update_post_meta($id, '_r3_r2_url', $remote);
            update_post_meta($id, '_r3_r2_width', $width);
            update_post_meta($id, '_r3_r2_height', $height);

            $deleted = array();
            if ($prune) $deleted = r3_r2_prune_local_files($id);

            return array(
                'ok' => true,
                'attachment_id' => $id,
                'remote_url' => $remote,
                'width' => $width,
                'height' => $height,
                'pruned' => $prune,
                'local_files_deleted' => $deleted,
            );
        }
    ));

    register_rest_route('runner3/v1', '/offload/(?P<id>\d+)', array(
        'methods' => 'GET',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function(WP_REST_Request $request) {
            $id = (int) $request['id'];
            return array(
                'attachment_id' => $id,
                'remote_url' => r3_r2_url($id),
                'width' => (int) get_post_meta($id, '_r3_r2_width', true),
                'height' => (int) get_post_meta($id, '_r3_r2_height', true),
                'local_file_exists' => (bool) ($file = get_attached_file($id)) && file_exists($file),
            );
        }
    ));
});
