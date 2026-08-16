<?php
if (!defined('ABSPATH')) { exit; }

function runner3_starter_setup(): void {
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script']);
    register_nav_menus(['primary' => __('Primary Menu', 'runner3-starter')]);
}
add_action('after_setup_theme', 'runner3_starter_setup');

function runner3_starter_assets(): void {
    wp_enqueue_style('runner3-starter', get_stylesheet_uri(), [], wp_get_theme()->get('Version'));
}
add_action('wp_enqueue_scripts', 'runner3_starter_assets');
