<?php
if (!defined('ABSPATH')) exit;

function runner3_editorial_setup() {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form','gallery','caption','style','script']);
    register_nav_menus(['primary' => __('Primary Menu', 'runner3-starter')]);
}
add_action('after_setup_theme', 'runner3_editorial_setup');

function runner3_editorial_assets() {
    wp_enqueue_style('runner3-editorial', get_stylesheet_uri(), [], '2.0.0');
}
add_action('wp_enqueue_scripts', 'runner3_editorial_assets');

function runner3_demo_images() {
    return [
        'https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1523726491678-bf852e717f6a?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1800&q=82',
        'https://images.unsplash.com/photo-1484417894907-623942c8ee29?auto=format&fit=crop&w=1800&q=82'
    ];
}

function runner3_story_image($post_id = 0, $offset = 0) {
    $post_id = $post_id ?: get_the_ID();
    if ($post_id && has_post_thumbnail($post_id)) {
        return get_the_post_thumbnail_url($post_id, 'large');
    }
    $images = runner3_demo_images();
    return $images[(absint($post_id) + absint($offset)) % count($images)];
}

function runner3_primary_fallback() {
    echo '<ul>';
    echo '<li><a href="' . esc_url(home_url('/#latest')) . '">Latest</a></li>';
    foreach (get_categories(['number' => 3, 'orderby' => 'count', 'order' => 'DESC']) as $cat) {
        echo '<li><a href="' . esc_url(get_category_link($cat)) . '">' . esc_html($cat->name) . '</a></li>';
    }
    $about = get_page_by_path('about');
    if ($about) echo '<li><a href="' . esc_url(get_permalink($about)) . '">About</a></li>';
    echo '</ul>';
}

function runner3_read_time($post_id = 0) {
    $post_id = $post_id ?: get_the_ID();
    $words = str_word_count(wp_strip_all_tags(get_post_field('post_content', $post_id)));
    return max(1, (int) ceil($words / 220));
}
