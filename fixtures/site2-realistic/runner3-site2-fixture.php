<?php
/**
 * Plugin Name: Runner3 Site2 Realistic Fixture
 * Description: Deterministic Astra + WooCommerce fixture used only for Runner3 Site2 performance-engine tests.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

define('RUNNER3_SITE2_FIXTURE_VERSION', 'astra-woo-v1');

add_action('admin_menu', function () {
    add_management_page(
        'Runner3 Site2 Fixture',
        'Runner3 Site2 Fixture',
        'manage_options',
        'runner3-site2-fixture',
        'runner3_site2_fixture_page'
    );
});

function runner3_site2_fixture_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    $message = '';
    if (isset($_POST['runner3_build'])) {
        check_admin_referer('runner3_site2_fixture_build');
        try {
            $summary = runner3_site2_fixture_build();
            $message = '<div class="notice notice-success"><p><strong>RUNNER3_SETUP_DONE</strong> '.esc_html(wp_json_encode($summary)).'</p></div>';
        } catch (Throwable $e) {
            $message = '<div class="notice notice-error"><p><strong>RUNNER3_SETUP_FAILED</strong> '.esc_html($e->getMessage()).'</p></div>';
        }
    }
    if (isset($_POST['runner3_reset'])) {
        check_admin_referer('runner3_site2_fixture_reset');
        $summary = runner3_site2_fixture_reset();
        $message = '<div class="notice notice-success"><p><strong>RUNNER3_RESET_DONE</strong> '.esc_html(wp_json_encode($summary)).'</p></div>';
    }
    echo '<div class="wrap"><h1>Runner3 Site2 Realistic Fixture</h1>'.$message;
    echo '<p>Target profile: Astra + WooCommerce + deterministic products, posts, pages, media and navigation.</p>';
    echo '<form method="post">';
    wp_nonce_field('runner3_site2_fixture_build');
    submit_button('Build realistic fixture', 'primary', 'runner3_build');
    echo '</form><hr><form method="post">';
    wp_nonce_field('runner3_site2_fixture_reset');
    submit_button('Reset fixture data', 'secondary', 'runner3_reset');
    echo '</form></div>';
}

function runner3_require_upgrader_bits() {
    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/plugin.php';
    require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
    require_once ABSPATH . 'wp-admin/includes/theme.php';
    require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
    require_once ABSPATH . 'wp-admin/includes/media.php';
    require_once ABSPATH . 'wp-admin/includes/image.php';
}

function runner3_install_theme($slug) {
    if (wp_get_theme($slug)->exists()) return;
    $api = themes_api('theme_information', array('slug' => $slug, 'fields' => array('sections' => false)));
    if (is_wp_error($api) || empty($api->download_link)) throw new Exception('Unable to resolve theme '.$slug);
    $skin = new Automatic_Upgrader_Skin();
    $upgrader = new Theme_Upgrader($skin);
    $result = $upgrader->install($api->download_link);
    if (is_wp_error($result) || !$result) throw new Exception('Unable to install theme '.$slug);
}

function runner3_install_plugin($slug, $plugin_file) {
    if (!file_exists(WP_PLUGIN_DIR.'/'.$plugin_file)) {
        $api = plugins_api('plugin_information', array('slug' => $slug, 'fields' => array('sections' => false)));
        if (is_wp_error($api) || empty($api->download_link)) throw new Exception('Unable to resolve plugin '.$slug);
        $skin = new Automatic_Upgrader_Skin();
        $upgrader = new Plugin_Upgrader($skin);
        $result = $upgrader->install($api->download_link);
        if (is_wp_error($result) || !$result) throw new Exception('Unable to install plugin '.$slug);
    }
    if (!is_plugin_active($plugin_file)) {
        $activated = activate_plugin($plugin_file);
        if (is_wp_error($activated)) throw new Exception('Unable to activate plugin '.$slug.': '.$activated->get_error_message());
    }
}

function runner3_fixture_marker($post_id) {
    update_post_meta($post_id, '_runner3_fixture', RUNNER3_SITE2_FIXTURE_VERSION);
}

function runner3_upsert_post($type, $slug, $title, $content, $status = 'publish') {
    $existing = get_page_by_path($slug, OBJECT, $type);
    $payload = array(
        'post_type' => $type,
        'post_name' => $slug,
        'post_title' => $title,
        'post_content' => $content,
        'post_status' => $status,
    );
    if ($existing) {
        $payload['ID'] = $existing->ID;
        $id = wp_update_post($payload, true);
    } else {
        $id = wp_insert_post($payload, true);
    }
    if (is_wp_error($id)) throw new Exception('Unable to create '.$type.' '.$slug.': '.$id->get_error_message());
    runner3_fixture_marker($id);
    return (int) $id;
}

function runner3_media_sources() {
    return array(
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/vneck-tee-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/hoodie-with-logo-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/tshirt-with-logo-1.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/beanie-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/belt-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/cap-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/sunglasses-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/hoodie-with-pocket-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/hoodie-with-zipper-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/long-sleeve-tee-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/polo-2.jpg',
        'https://woocommercecore.mystagingwebsite.com/wp-content/uploads/2017/12/album-1.jpg'
    );
}

function runner3_ensure_media() {
    $ids = array();
    foreach (runner3_media_sources() as $index => $url) {
        $key = '_runner3_fixture_media_'.$index;
        $existing = (int) get_option($key, 0);
        if ($existing && get_post($existing)) {
            $ids[] = $existing;
            continue;
        }
        $tmp = download_url($url, 45);
        if (is_wp_error($tmp)) continue;
        $file = array('name' => 'runner3-product-'.($index + 1).'.jpg', 'tmp_name' => $tmp);
        $id = media_handle_sideload($file, 0, 'Runner3 product image '.($index + 1));
        if (is_wp_error($id)) {
            @unlink($tmp);
            continue;
        }
        runner3_fixture_marker($id);
        update_option($key, (int) $id, false);
        $ids[] = (int) $id;
    }
    if (count($ids) < 6) throw new Exception('Fixture requires at least 6 product images; got '.count($ids));
    return $ids;
}

function runner3_ensure_product_categories() {
    $names = array('Apparel', 'Accessories', 'Essentials', 'Outdoor', 'Studio', 'Travel');
    $map = array();
    foreach ($names as $name) {
        $slug = sanitize_title($name);
        $term = get_term_by('slug', $slug, 'product_cat');
        if (!$term) {
            $created = wp_insert_term($name, 'product_cat', array('slug' => $slug));
            if (is_wp_error($created)) throw new Exception('Unable to create product category '.$name);
            $term = get_term($created['term_id'], 'product_cat');
        }
        $map[$slug] = (int) $term->term_id;
        update_term_meta($term->term_id, '_runner3_fixture', RUNNER3_SITE2_FIXTURE_VERSION);
    }
    return $map;
}

function runner3_ensure_products($media_ids, $category_map) {
    if (!class_exists('WC_Product_Simple')) throw new Exception('WooCommerce classes unavailable after activation');
    $adjectives = array('Everyday', 'Trail', 'Studio', 'Classic', 'Essential', 'Coastal');
    $nouns = array('Tee', 'Hoodie', 'Cap', 'Pack', 'Jacket', 'Bottle');
    $cat_slugs = array_keys($category_map);
    $ids = array();
    for ($i = 1; $i <= 36; $i++) {
        $sku = sprintf('R3-S2-%03d', $i);
        $existing_id = wc_get_product_id_by_sku($sku);
        $product = $existing_id ? wc_get_product($existing_id) : new WC_Product_Simple();
        if (!$product) $product = new WC_Product_Simple();
        $name = $adjectives[($i - 1) % count($adjectives)].' '.$nouns[(int)(($i - 1) / 6) % count($nouns)].' '.$i;
        $price = 24 + (($i * 7) % 70) + .99;
        $product->set_name($name);
        $product->set_sku($sku);
        $product->set_status('publish');
        $product->set_catalog_visibility('visible');
        $product->set_regular_price((string) $price);
        if ($i % 5 === 0) $product->set_sale_price((string) round($price * .82, 2)); else $product->set_sale_price('');
        $product->set_manage_stock(true);
        $product->set_stock_quantity(12 + (($i * 11) % 90));
        $product->set_weight((string) (0.2 + (($i % 8) * .15)));
        $product->set_short_description('A realistic fixture product for storefront, catalog and performance regression testing.');
        $product->set_description(str_repeat('Built for realistic WooCommerce rendering tests with pricing, inventory, category data, media and responsive product cards. ', 5));
        $product->set_category_ids(array($category_map[$cat_slugs[($i - 1) % count($cat_slugs)]]));
        $product->set_image_id($media_ids[($i - 1) % count($media_ids)]);
        $product->set_gallery_image_ids(array(
            $media_ids[$i % count($media_ids)],
            $media_ids[($i + 3) % count($media_ids)],
        ));
        $product->set_featured($i <= 8);
        $id = $product->save();
        runner3_fixture_marker($id);
        $ids[] = (int) $id;
    }
    return $ids;
}

function runner3_article_content($index) {
    $para = 'Performance engineering works best on representative content rather than an empty theme. This fixture deliberately combines editorial copy, product media, navigation, WooCommerce queries and responsive components so optimization decisions have a meaningful baseline.';
    return '<p>'.implode('</p><p>', array_fill(0, 8, $para.' Article '.$index.'.')).'</p><h2>Field notes</h2><p>'.str_repeat($para.' ', 4).'</p>';
}

function runner3_ensure_blog($media_ids) {
    $category = term_exists('Field Notes', 'category');
    if (!$category) $category = wp_insert_term('Field Notes', 'category', array('slug' => 'field-notes'));
    $cat_id = is_array($category) ? (int)$category['term_id'] : (int)$category;
    $ids = array();
    for ($i = 1; $i <= 12; $i++) {
        $id = runner3_upsert_post('post', 'field-note-'.$i, 'Field Note '.$i, runner3_article_content($i));
        wp_set_post_categories($id, array($cat_id));
        set_post_thumbnail($id, $media_ids[($i - 1) % count($media_ids)]);
        $ids[] = $id;
    }
    return $ids;
}

function runner3_ensure_pages($media_ids) {
    $hero = esc_url(wp_get_attachment_url($media_ids[0]));
    $home = '<div class="runner3-fixture-home">'
        .'<section style="min-height:520px;padding:80px 7%;display:flex;align-items:center;background:#111;color:#fff;background-image:linear-gradient(90deg,rgba(0,0,0,.8),rgba(0,0,0,.18)),url('.$hero.');background-size:cover;background-position:center"><div style="max-width:680px"><p>RUNNER3 COMMERCE LAB</p><h1 style="font-size:clamp(44px,7vw,82px);line-height:1">Everyday goods, built for the long run.</h1><p style="font-size:20px">A realistic WooCommerce storefront fixture for performance engineering.</p><p><a style="display:inline-block;padding:14px 24px;background:#fff;color:#111;text-decoration:none" href="/shop/">Shop collection</a></p></div></section>'
        .'<section style="padding:64px 5%"><h2>Shop by category</h2>[product_categories number="6" columns="3" hide_empty="0"]</section>'
        .'<section style="padding:64px 5%;background:#f5f5f5"><h2>Featured products</h2>[products limit="12" columns="4" visibility="featured"]</section>'
        .'<section style="padding:64px 8%;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:30px"><div><h3>Fast dispatch</h3><p>Sample merchandising content for realistic layout and font rendering.</p></div><div><h3>Thoughtful materials</h3><p>Representative copy adds DOM depth without artificial benchmark-only markup.</p></div><div><h3>Simple returns</h3><p>Commerce content keeps the fixture closer to a real client site.</p></div></section>'
        .'<section style="padding:64px 5%"><h2>Latest field notes</h2>[display-posts posts_per_page="3"]</section>'
        .'</div>';
    $pages = array();
    $pages['home'] = runner3_upsert_post('page', 'home', 'Home', $home);
    $pages['about'] = runner3_upsert_post('page', 'about', 'About', '<h1>About Runner3 Commerce Lab</h1>'.runner3_article_content(20));
    $pages['contact'] = runner3_upsert_post('page', 'contact', 'Contact', '<h1>Contact</h1><p>hello@example.test</p><p>123 Performance Avenue</p>'.runner3_article_content(21));
    $pages['faq'] = runner3_upsert_post('page', 'faq', 'FAQ', '<h1>Frequently Asked Questions</h1><h2>Shipping</h2><p>Orders normally leave the warehouse within two business days.</p><h2>Returns</h2><p>Returns are accepted within 30 days.</p>'.runner3_article_content(22));
    $pages['journal'] = runner3_upsert_post('page', 'journal', 'Journal', '<h1>Journal</h1><p>Editorial landing page for the fixture blog.</p>');
    update_option('show_on_front', 'page');
    update_option('page_on_front', $pages['home']);
    return $pages;
}

function runner3_ensure_menu($pages) {
    $menu = wp_get_nav_menu_object('Runner3 Primary');
    $menu_id = $menu ? (int)$menu->term_id : (int)wp_create_nav_menu('Runner3 Primary');
    $wanted = array(
        array('title' => 'Home', 'object_id' => $pages['home'], 'object' => 'page', 'type' => 'post_type'),
        array('title' => 'Shop', 'object_id' => (int)wc_get_page_id('shop'), 'object' => 'page', 'type' => 'post_type'),
        array('title' => 'About', 'object_id' => $pages['about'], 'object' => 'page', 'type' => 'post_type'),
        array('title' => 'Journal', 'object_id' => $pages['journal'], 'object' => 'page', 'type' => 'post_type'),
        array('title' => 'Contact', 'object_id' => $pages['contact'], 'object' => 'page', 'type' => 'post_type'),
    );
    $existing = wp_get_nav_menu_items($menu_id) ?: array();
    $existing_ids = array_map(function($item){ return (int)$item->object_id; }, $existing);
    foreach ($wanted as $item) {
        if (in_array((int)$item['object_id'], $existing_ids, true)) continue;
        wp_update_nav_menu_item($menu_id, 0, array(
            'menu-item-title' => $item['title'],
            'menu-item-object-id' => $item['object_id'],
            'menu-item-object' => $item['object'],
            'menu-item-type' => $item['type'],
            'menu-item-status' => 'publish',
        ));
    }
    $locations = get_theme_mod('nav_menu_locations', array());
    $registered = get_registered_nav_menus();
    $target = isset($registered['primary']) ? 'primary' : (isset($registered['primary-menu']) ? 'primary-menu' : array_key_first($registered));
    if ($target) {
        $locations[$target] = $menu_id;
        set_theme_mod('nav_menu_locations', $locations);
    }
}

function runner3_site2_fixture_build() {
    runner3_require_upgrader_bits();
    if (!get_option('runner3_site2_fixture_previous_theme')) update_option('runner3_site2_fixture_previous_theme', get_stylesheet(), false);
    runner3_install_theme('astra');
    switch_theme('astra');
    runner3_install_plugin('woocommerce', 'woocommerce/woocommerce.php');
    if (!class_exists('WooCommerce')) throw new Exception('WooCommerce activation did not load');
    if (class_exists('WC_Install')) WC_Install::create_pages();

    update_option('blogname', 'Runner3 Commerce Lab');
    update_option('blogdescription', 'A realistic WooCommerce performance engineering fixture');
    update_option('permalink_structure', '/%postname%/');
    update_option('woocommerce_currency', 'USD');
    update_option('woocommerce_enable_guest_checkout', 'yes');
    update_option('woocommerce_default_country', 'US:CA');
    flush_rewrite_rules(false);

    $media = runner3_ensure_media();
    $categories = runner3_ensure_product_categories();
    $products = runner3_ensure_products($media, $categories);
    $posts = runner3_ensure_blog($media);
    $pages = runner3_ensure_pages($media);
    runner3_ensure_menu($pages);

    $hello = get_page_by_path('hello-world', OBJECT, 'post');
    if ($hello) wp_trash_post($hello->ID);
    $sample = get_page_by_path('sample-page', OBJECT, 'page');
    if ($sample) wp_trash_post($sample->ID);

    update_option('runner3_site2_fixture_version', RUNNER3_SITE2_FIXTURE_VERSION, false);
    update_option('runner3_site2_fixture_built_at', gmdate('c'), false);

    return array(
        'fixture' => RUNNER3_SITE2_FIXTURE_VERSION,
        'theme' => get_stylesheet(),
        'woocommerce' => defined('WC_VERSION') ? WC_VERSION : null,
        'media' => count($media),
        'products' => count($products),
        'posts' => count($posts),
        'pages' => count($pages),
    );
}

function runner3_site2_fixture_reset() {
    $query = new WP_Query(array(
        'post_type' => 'any',
        'post_status' => 'any',
        'posts_per_page' => -1,
        'meta_key' => '_runner3_fixture',
        'meta_value' => RUNNER3_SITE2_FIXTURE_VERSION,
        'fields' => 'ids',
    ));
    $deleted = 0;
    foreach ($query->posts as $id) {
        if (wp_delete_post($id, true)) $deleted++;
    }
    $terms = get_terms(array('taxonomy' => 'product_cat', 'hide_empty' => false, 'meta_key' => '_runner3_fixture', 'meta_value' => RUNNER3_SITE2_FIXTURE_VERSION));
    if (!is_wp_error($terms)) foreach ($terms as $term) wp_delete_term($term->term_id, 'product_cat');
    $menu = wp_get_nav_menu_object('Runner3 Primary');
    if ($menu) wp_delete_nav_menu($menu->term_id);
    $previous = get_option('runner3_site2_fixture_previous_theme');
    if ($previous && wp_get_theme($previous)->exists()) switch_theme($previous);
    delete_option('runner3_site2_fixture_version');
    delete_option('runner3_site2_fixture_built_at');
    return array('deleted_posts_products_media' => $deleted, 'theme' => get_stylesheet());
}
