<?php
/**
 * Plugin Name: Runner3 Bootstrap
 * Description: One-time bootstrap for the Runner3 starter site.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) { exit; }

function runner3_ensure_page(string $slug, string $title, string $content): int {
    $existing = get_page_by_path($slug, OBJECT, 'page');
    if ($existing instanceof WP_Post) {
        return (int) $existing->ID;
    }

    $id = wp_insert_post([
        'post_type' => 'page',
        'post_status' => 'publish',
        'post_name' => $slug,
        'post_title' => $title,
        'post_content' => $content,
    ], true);

    return is_wp_error($id) ? 0 : (int) $id;
}

function runner3_bootstrap_site(): void {
    if (get_option('runner3_bootstrap_done')) {
        return;
    }

    $theme = wp_get_theme('runner3-starter');
    if ($theme->exists() && get_stylesheet() !== 'runner3-starter') {
        switch_theme('runner3-starter');
    }

    $home_id = runner3_ensure_page('home', 'Home', 'Welcome. This site is managed through the Runner3 WordPress workflow.');
    runner3_ensure_page('about', 'About', '<h2>About</h2><p>Replace this starter text with the real site description.</p>');
    runner3_ensure_page('contact', 'Contact', '<h2>Contact</h2><p>Add the preferred contact details here.</p>');

    if ($home_id > 0) {
        update_option('show_on_front', 'page');
        update_option('page_on_front', $home_id);
    }

    if (get_option('blogdescription') === 'Just another WordPress site') {
        update_option('blogdescription', 'Built and deployed with Runner3.');
    }

    update_option('runner3_bootstrap_done', gmdate('c'));
}
add_action('init', 'runner3_bootstrap_site', 20);
