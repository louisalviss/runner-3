<?php
/**
 * Plugin Name: Site2 Benchmark Seed
 * Description: Deterministic one-shot Astra/WooCommerce benchmark content seed for runner3 Site 2.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

define('SITE2_BENCHMARK_VERSION', 'astra-woocommerce-gutenberg-v1');

function site2_fixture_image($key, $label, $index, $width = 1280, $height = 853) {
    $existing = get_posts([
        'post_type' => 'attachment', 'post_status' => 'inherit', 'posts_per_page' => 1,
        'meta_key' => '_site2_fixture_key', 'meta_value' => $key, 'fields' => 'ids',
    ]);
    if ($existing) return (int) $existing[0];

    if (!function_exists('imagecreatetruecolor')) {
        throw new Exception('php_gd_missing');
    }

    $uploads = wp_upload_dir();
    if (!empty($uploads['error'])) throw new Exception('uploads_unavailable:' . $uploads['error']);
    $dir = trailingslashit($uploads['path']);
    wp_mkdir_p($dir);
    $filename = 'site2-' . sanitize_file_name($key) . '.jpg';
    $path = $dir . $filename;

    $im = imagecreatetruecolor($width, $height);
    $r1 = 45 + (($index * 31) % 105); $g1 = 55 + (($index * 43) % 110); $b1 = 70 + (($index * 53) % 110);
    $r2 = 150 + (($index * 17) % 90); $g2 = 135 + (($index * 23) % 100); $b2 = 120 + (($index * 29) % 110);
    for ($y = 0; $y < $height; $y++) {
        $t = $y / max(1, $height - 1);
        $r = (int) round($r1 * (1 - $t) + $r2 * $t);
        $g = (int) round($g1 * (1 - $t) + $g2 * $t);
        $b = (int) round($b1 * (1 - $t) + $b2 * $t);
        $color = imagecolorallocate($im, $r, $g, $b);
        imageline($im, 0, $y, $width, $y, $color);
    }
    mt_srand(8200 + $index);
    for ($i = 0; $i < 650; $i++) {
        $x = mt_rand(0, $width); $y = mt_rand(0, $height);
        $w = mt_rand(8, 95); $h = mt_rand(8, 95);
        $color = imagecolorallocatealpha($im, mt_rand(30, 240), mt_rand(30, 240), mt_rand(30, 240), mt_rand(85, 118));
        imagefilledellipse($im, $x, $y, $w, $h, $color);
    }
    $overlay = imagecolorallocatealpha($im, 0, 0, 0, 65);
    imagefilledrectangle($im, 0, $height - 150, $width, $height, $overlay);
    $white = imagecolorallocate($im, 255, 255, 255);
    imagestring($im, 5, 48, $height - 105, $label, $white);
    imagestring($im, 3, 48, $height - 68, 'Site 2 realistic WooCommerce benchmark fixture', $white);
    if (!imagejpeg($im, $path, 82)) { imagedestroy($im); throw new Exception('fixture_jpeg_write_failed'); }
    imagedestroy($im);

    $filetype = wp_check_filetype($filename, null);
    $attachment_id = wp_insert_attachment([
        'post_mime_type' => $filetype['type'] ?: 'image/jpeg',
        'post_title' => $label,
        'post_content' => '',
        'post_status' => 'inherit',
    ], $path);
    if (is_wp_error($attachment_id)) throw new Exception('attachment_insert_failed:' . $attachment_id->get_error_message());
    require_once ABSPATH . 'wp-admin/includes/image.php';
    $meta = wp_generate_attachment_metadata($attachment_id, $path);
    wp_update_attachment_metadata($attachment_id, $meta);
    update_post_meta($attachment_id, '_wp_attachment_image_alt', $label . ' benchmark image');
    update_post_meta($attachment_id, '_site2_fixture_key', $key);
    return (int) $attachment_id;
}

function site2_upsert_page($slug, $title, $content) {
    $existing = get_page_by_path($slug, OBJECT, 'page');
    $args = ['post_type' => 'page', 'post_status' => 'publish', 'post_title' => $title, 'post_name' => $slug, 'post_content' => $content];
    if ($existing) { $args['ID'] = $existing->ID; $id = wp_update_post($args, true); }
    else $id = wp_insert_post($args, true);
    if (is_wp_error($id)) throw new Exception('page_write_failed:' . $slug . ':' . $id->get_error_message());
    return (int) $id;
}

function site2_upsert_post($slug, $title, $content, $featured = 0) {
    $found = get_page_by_path($slug, OBJECT, 'post');
    $args = ['post_type' => 'post', 'post_status' => 'publish', 'post_title' => $title, 'post_name' => $slug, 'post_content' => $content];
    if ($found) { $args['ID'] = $found->ID; $id = wp_update_post($args, true); }
    else $id = wp_insert_post($args, true);
    if (is_wp_error($id)) throw new Exception('post_write_failed:' . $slug . ':' . $id->get_error_message());
    if ($featured) set_post_thumbnail($id, $featured);
    return (int) $id;
}

function site2_category($name, $slug) {
    $term = term_exists($slug, 'product_cat');
    if (!$term) $term = wp_insert_term($name, 'product_cat', ['slug' => $slug]);
    if (is_wp_error($term)) throw new Exception('category_failed:' . $slug . ':' . $term->get_error_message());
    return (int) (is_array($term) ? $term['term_id'] : $term);
}

function site2_simple_product($spec) {
    $id = wc_get_product_id_by_sku($spec['sku']);
    $product = $id ? wc_get_product($id) : new WC_Product_Simple();
    if (!$product || !is_a($product, 'WC_Product')) throw new Exception('product_load_failed:' . $spec['sku']);
    $product->set_name($spec['name']);
    $product->set_slug(sanitize_title($spec['name']));
    $product->set_sku($spec['sku']);
    $product->set_status('publish');
    $product->set_catalog_visibility('visible');
    $product->set_description('<p>' . esc_html($spec['name']) . ' is realistic sample catalog content for repeatable WordPress and WooCommerce performance testing.</p><p>It includes imagery, taxonomy, inventory and pricing metadata representative of a small production store.</p>');
    $product->set_short_description('<p>Everyday ' . esc_html(strtolower($spec['name'])) . ' for the Northstar benchmark store.</p>');
    $product->set_regular_price($spec['price']);
    $product->set_sale_price($spec['sale']);
    $product->set_featured($spec['featured']);
    $product->set_category_ids([$spec['category']]);
    $product->set_image_id($spec['image']);
    $product->set_manage_stock(true);
    $product->set_stock_quantity($spec['stock']);
    $product->set_stock_status('instock');
    $product->set_weight($spec['weight']);
    return (int) $product->save();
}

function site2_variable_product($spec) {
    $id = wc_get_product_id_by_sku($spec['sku']);
    $product = $id ? wc_get_product($id) : new WC_Product_Variable();
    if (!$product || !is_a($product, 'WC_Product_Variable')) {
        if ($id) wp_delete_post($id, true);
        $product = new WC_Product_Variable();
    }
    $product->set_name($spec['name']);
    $product->set_slug(sanitize_title($spec['name']));
    $product->set_sku($spec['sku']);
    $product->set_status('publish');
    $product->set_catalog_visibility('visible');
    $product->set_description('<p>' . esc_html($spec['name']) . ' is a variable sample product with multiple size options for realistic WooCommerce testing.</p>');
    $product->set_short_description('<p>Three-size benchmark variable product.</p>');
    $product->set_featured($spec['featured']);
    $product->set_category_ids([$spec['category']]);
    $product->set_image_id($spec['image']);
    $attribute = new WC_Product_Attribute();
    $attribute->set_id(0); $attribute->set_name('Size'); $attribute->set_options(['S', 'M', 'L']);
    $attribute->set_position(0); $attribute->set_visible(true); $attribute->set_variation(true);
    $product->set_attributes([$attribute]);
    $product_id = (int) $product->save();
    foreach (['S', 'M', 'L'] as $j => $size) {
        $vsku = $spec['sku'] . '-' . $size;
        $vid = wc_get_product_id_by_sku($vsku);
        $variation = $vid ? new WC_Product_Variation($vid) : new WC_Product_Variation();
        $variation->set_parent_id($product_id);
        $variation->set_sku($vsku);
        $variation->set_status('publish');
        $variation->set_regular_price(number_format((float)$spec['price'] + ($j * 3), 2, '.', ''));
        $variation->set_manage_stock(true); $variation->set_stock_quantity(8 + ($j * 3)); $variation->set_stock_status('instock');
        $variation->set_attributes(['size' => $size]);
        $variation->save();
    }
    WC_Product_Variable::sync($product_id);
    return $product_id;
}

function site2_seed_menu($page_ids) {
    $menu = wp_get_nav_menu_object('Northstar Primary');
    if ($menu) wp_delete_nav_menu($menu->term_id);
    $menu_id = wp_create_nav_menu('Northstar Primary');
    if (is_wp_error($menu_id)) throw new Exception('menu_create_failed:' . $menu_id->get_error_message());
    foreach (['home','shop','about','blog','contact'] as $key) {
        wp_update_nav_menu_item($menu_id, 0, [
            'menu-item-object-id' => $page_ids[$key], 'menu-item-object' => 'page',
            'menu-item-type' => 'post_type', 'menu-item-status' => 'publish',
        ]);
    }
    $locations = get_theme_mod('nav_menu_locations', []);
    $registered = get_registered_nav_menus();
    $location = isset($registered['primary']) ? 'primary' : (isset($registered['primary-menu']) ? 'primary-menu' : array_key_first($registered));
    if ($location) { $locations[$location] = $menu_id; set_theme_mod('nav_menu_locations', $locations); }
}

function site2_seed_all() {
    if (!class_exists('WooCommerce') || !class_exists('WC_Product_Simple')) throw new Exception('woocommerce_not_active');

    foreach (['hello-world'] as $slug) {
        $p = get_page_by_path($slug, OBJECT, 'post'); if ($p) wp_trash_post($p->ID);
    }
    $sample = get_page_by_path('sample-page', OBJECT, 'page'); if ($sample) wp_trash_post($sample->ID);

    $images = [];
    $images[] = site2_fixture_image('fixture-hero', 'Northstar Store Hero', 1, 1600, 1000);
    for ($i = 1; $i <= 8; $i++) $images[] = site2_fixture_image('product-' . sprintf('%02d', $i), 'Northstar Product ' . sprintf('%02d', $i), $i + 1);
    $hero = wp_get_attachment_url($images[0]);

    $home = '<!-- wp:cover {"url":"' . esc_url($hero) . '","id":' . $images[0] . ',"dimRatio":45,"minHeight":560,"minHeightUnit":"px","align":"full"} --><div class="wp-block-cover alignfull" style="min-height:560px"><span aria-hidden="true" class="wp-block-cover__background has-background-dim-40 has-background-dim"></span><img class="wp-block-cover__image-background wp-image-' . $images[0] . '" alt="Northstar Store Hero benchmark image" src="' . esc_url($hero) . '" data-object-fit="cover"/><div class="wp-block-cover__inner-container"><!-- wp:heading {"textAlign":"center","level":1} --><h1 class="wp-block-heading has-text-align-center">Northstar Everyday Goods</h1><!-- /wp:heading --><!-- wp:paragraph {"align":"center"} --><p class="has-text-align-center">A realistic WooCommerce benchmark storefront built for repeatable performance testing.</p><!-- /wp:paragraph --></div></div><!-- /wp:cover --><!-- wp:spacer {"height":"48px"} --><div style="height:48px" aria-hidden="true" class="wp-block-spacer"></div><!-- /wp:spacer --><!-- wp:heading {"textAlign":"center"} --><h2 class="wp-block-heading has-text-align-center">Featured products</h2><!-- /wp:heading --><!-- wp:shortcode -->[products limit="8" columns="4" visibility="featured"]<!-- /wp:shortcode --><!-- wp:columns --><div class="wp-block-columns"><!-- wp:column --><div class="wp-block-column"><h3>Built for everyday use</h3><p>Durable essentials with straightforward materials, sizing and care information.</p></div><!-- /wp:column --><!-- wp:column --><div class="wp-block-column"><h3>Simple shipping</h3><p>Representative store messaging creates a realistic document structure.</p></div><!-- /wp:column --><!-- wp:column --><div class="wp-block-column"><h3>30-product catalog</h3><p>Categories, sales, variable products and media are included.</p></div><!-- /wp:column --></div><!-- /wp:columns -->';

    $pages = [];
    $pages['home'] = site2_upsert_page('home', 'Home', $home);
    $pages['shop'] = site2_upsert_page('shop', 'Shop', '<!-- wp:heading --><h1 class="wp-block-heading">Shop</h1><!-- /wp:heading --><!-- wp:shortcode -->[products limit="12" columns="4" paginate="true"]<!-- /wp:shortcode -->');
    $pages['about'] = site2_upsert_page('about', 'About', '<h1>About Northstar</h1><p>Northstar is deterministic sample storefront content used to test WordPress and WooCommerce performance changes.</p>');
    $pages['contact'] = site2_upsert_page('contact', 'Contact', '<h1>Contact</h1><p>Email hello@example.test. This is benchmark content, not a live commercial store.</p>');
    $pages['cart'] = site2_upsert_page('cart', 'Cart', '[woocommerce_cart]');
    $pages['checkout'] = site2_upsert_page('checkout', 'Checkout', '[woocommerce_checkout]');
    $pages['my-account'] = site2_upsert_page('my-account', 'My Account', '[woocommerce_my_account]');
    $pages['blog'] = site2_upsert_page('blog', 'Blog', '<h1>Journal</h1><p>Store stories, product notes and care guides.</p>');

    update_option('show_on_front', 'page'); update_option('page_on_front', $pages['home']); update_option('page_for_posts', $pages['blog']);
    update_option('blogname', 'Northstar Store'); update_option('blogdescription', 'Realistic Site 2 WooCommerce benchmark');
    update_option('woocommerce_shop_page_id', $pages['shop']); update_option('woocommerce_cart_page_id', $pages['cart']);
    update_option('woocommerce_checkout_page_id', $pages['checkout']); update_option('woocommerce_myaccount_page_id', $pages['my-account']);
    update_option('woocommerce_currency', 'USD'); update_option('woocommerce_default_country', 'US:CA');

    $post_titles = ['How we choose everyday materials','A practical guide to layering','Packing lighter for a weekend','Care notes for daily essentials','Building a compact travel kit','Simple color combinations','Desk-to-weekend essentials','Five ways to organize your carry'];
    foreach ($post_titles as $i => $title) {
        site2_upsert_post('northstar-journal-' . sprintf('%02d', $i + 1), $title, '<p>This benchmark article provides realistic editorial content for Site 2.</p><p>Performance tests should preserve content and visual hierarchy while optimizing delivery.</p>', $images[1 + ($i % 8)]);
    }

    $cats = [];
    foreach ([['Apparel','apparel'],['Accessories','accessories'],['Home & Desk','home-desk'],['Travel','travel'],['Outdoor','outdoor'],['Sale','sale']] as $c) $cats[$c[1]] = site2_category($c[0], $c[1]);
    $cat_slugs = array_keys($cats);
    $names = ['Canvas Daypack','Merino Crew Tee','Everyday Bottle','Trail Cap','Desk Organizer','Travel Pouch','Weekend Tote','Softshell Jacket','Utility Overshirt','Camp Mug','Tech Sleeve','Packing Cubes','Wool Beanie','Field Notebook','Cable Kit','Commuter Backpack','Relaxed Hoodie','Classic Socks','Travel Tumbler','Compact Umbrella','Laptop Stand','Minimal Wallet','Gym Duffel','Lightweight Scarf','Everyday Sneaker','Layering Tee','Trail Shorts','Travel Chino','Core Sweatshirt','Field Jacket'];
    $variable_indexes = [1,8,16,28];
    foreach ($names as $i => $name) {
        $price = 24 + (($i * 7) % 86);
        $spec = [
            'name' => $name, 'sku' => 'S2-' . sprintf('%03d', $i + 1), 'price' => number_format($price, 2, '.', ''),
            'sale' => ($i % 5 === 0) ? number_format($price * 0.82, 2, '.', '') : '',
            'featured' => $i < 8, 'category' => $cats[$cat_slugs[$i % count($cat_slugs)]],
            'image' => $images[1 + ($i % 8)], 'stock' => 15 + ($i % 12), 'weight' => number_format(0.2 + (($i % 8) * 0.15), 2, '.', ''),
        ];
        if (in_array($i, $variable_indexes, true)) site2_variable_product($spec); else site2_simple_product($spec);
    }

    site2_seed_menu($pages);
    delete_transient('wc_products_onsale');
    if (function_exists('wc_delete_product_transients')) wc_delete_product_transients();
    flush_rewrite_rules(false);
    update_option('site2_benchmark_fixture_version', SITE2_BENCHMARK_VERSION, false);
    update_option('site2_benchmark_fixture_seeded_at', gmdate('c'), false);
}

function site2_fixture_status() {
    $products = get_posts(['post_type' => 'product', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids']);
    $variable = 0; foreach ($products as $id) { $p = wc_get_product($id); if ($p && $p->is_type('variable')) $variable++; }
    $pages = get_posts(['post_type' => 'page', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids']);
    $posts = get_posts(['post_type' => 'post', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids']);
    $media = get_posts(['post_type' => 'attachment', 'post_status' => 'inherit', 'posts_per_page' => -1, 'meta_key' => '_site2_fixture_key', 'fields' => 'ids']);
    $categories = get_terms(['taxonomy' => 'product_cat', 'hide_empty' => false]);
    $theme = wp_get_theme();
    return [
        'version' => get_option('site2_benchmark_fixture_version'), 'seeded_at' => get_option('site2_benchmark_fixture_seeded_at'),
        'theme' => $theme->get_stylesheet(), 'theme_version' => $theme->get('Version'),
        'woocommerce' => defined('WC_VERSION') ? WC_VERSION : null,
        'counts' => ['pages' => count($pages), 'posts' => count($posts), 'products' => count($products), 'variable_products' => $variable, 'categories' => is_wp_error($categories) ? 0 : count($categories), 'fixture_media' => count($media)],
    ];
}

register_activation_hook(__FILE__, function() {
    try { site2_seed_all(); }
    catch (Throwable $e) { update_option('site2_benchmark_fixture_error', $e->getMessage(), false); throw $e; }
});

add_action('rest_api_init', function() {
    register_rest_route('site2-benchmark/v1', '/status', [
        'methods' => 'GET', 'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function() { return rest_ensure_response(site2_fixture_status()); },
    ]);
});
