let BASE_URL = "https://tienvuc.me";
try {
    if (DOMAIN) BASE_URL = String(DOMAIN).replace(/\/$/, "");
} catch (error) {
}

function normalizeUrl(url) {
    url = String(url || "");
    if (!url) return BASE_URL;
    if (url.indexOf("http://") === 0 || url.indexOf("https://") === 0) {
        return url.replace(/^https?:\/\/[^\/]+/i, BASE_URL);
    }
    if (url.charAt(0) !== "/") url = "/" + url;
    return BASE_URL + url;
}

function getSlug(url) {
    let normalized = normalizeUrl(url);
    let path = normalized.replace(/^https?:\/\/[^\/]+/i, "").split("?")[0].split("#")[0];
    let parts = path.split("/");
    return parts.length > 1 ? parts[1] : "";
}

function coverUrl(cover) {
    if (!cover) return "";
    if (cover.domain && cover.url) return String(cover.domain).replace(/\/$/, "") + "/" + String(cover.url).replace(/^\//, "");
    if (cover.noImg) return String(cover.noImg);
    return "";
}

function bookItem(book) {
    let vip = book && book.vip === true ? "【VIP】 " : "";
    let author = book && book.author && book.author.name ? String(book.author.name) : "";
    let slug = book && book.slug ? String(book.slug) : "";
    return {
        name: book && book.name ? String(book.name) : slug,
        link: BASE_URL + "/" + slug,
        cover: coverUrl(book ? book.cover : null),
        description: vip + author
    };
}
