function execute(input, page) {
    page = page || "1";
    var split = String(input).indexOf("|");
    if (split < 1) return Response.error("Input nguồn không hợp lệ");
    var id = String(input).substring(0, split);
    var path = String(input).substring(split + 1);
    var host = sourceHost(id);
    var response = fetch(buildListUrl(id, host, path, page));
    if (!response.ok) return Response.error("HTTP " + response.status);
    var data = parseSourceItems(response.html(), host, id);
    if (id === "comong") enrichComongCovers(data, page);
    return Response.success(data, data.length ? String(parseInt(page, 10) + 1) : "");
}

function enrichComongCovers(data, page) {
    var covers = {};
    collectComongCoverPage(parseInt(page, 10), covers);
    collectComongCoverPage(parseInt(page, 10) + 1, covers);
    collectComongCoverApi(covers);
    for (var i = 0; i < data.length; i++) {
        if (!data[i].cover) data[i].cover = covers[sourceSlug(data[i].link)] || "https://comong.info/wp-content/uploads/2025/05/logo-comong.info_.png";
    }
}

function collectComongCoverApi(covers) {
    try {
        var response = Http.get("https://comong.info/wp-json/wp/v2/posts?per_page=100&_embed=wp:featuredmedia");
        var items = JSON.parse(response.string());
        for (var i = 0; i < items.length; i++) {
            var media = items[i]._embedded && items[i]._embedded["wp:featuredmedia"];
            if (media && media.length && media[0].source_url) covers[sourceSlug(items[i].link)] = media[0].source_url;
        }
    } catch (error) {}
}

function collectComongCoverPage(page, covers) {
    var url = page === 1 ? "https://comong.info/" : "https://comong.info/page/" + page + "/";
    var response = fetch(url);
    if (!response.ok) return;
    response.html().select(".post-item").forEach(function(item) {
        var link = item.select("a.plain").first();
        var image = item.select("img").first();
        if (!link || !image) return;
        var cover = image.attr("data-src") || image.attr("src") || "";
        if (cover && cover.indexOf("data:image/") !== 0) covers[sourceSlug(link.attr("href"))] = cover;
    });
}

function sourceSlug(url) {
    var value = String(url || "").replace(/[?#].*$/, "").replace(/\/$/, "");
    return value.substring(value.lastIndexOf("/") + 1);
}

function sourceHost(id) {
    var hosts = {
        bachngoclau: "https://bachngoclau.com", comong: "https://comong.site", comonginfo: "https://comong.info",
        doctruyen: "https://doctruyen.shop", doctruyenchill: "https://www.doctruyenchill.net",
        laophatgia: "https://laophatgia.fit", metruyen: "https://metruyen.fit",
        monkeyd: "https://www.monkeydd.com", mottruyen: "https://mottruyen.top",
        nangtho: "https://nangtho.site", otruyen: "https://otruyen.online",
        saytruyen: "https://saytruyen.vn", tanmong: "https://yeungontinh.site",
        tiemchungot: "https://tiemchungot.com", tieuhoadan: "https://tieuhoadan.com",
        truyendexuat: "https://truyendexuat.com", truyentv: "https://truyentv.site",
        vanmonglau: "https://vanmonglau.com", vivutruyen: "https://vivutruyen.net"
    };
    return hosts[id] || "";
}

function buildListUrl(id, host, path, page) {
    var url = path.indexOf("http") === 0 ? path : host + (path.charAt(0) === "/" ? path : "/" + path);
    if (id === "monkeyd") return host + "/" + path.replace(/\.html$/, "") + ".html?page=" + page;
    if (page === "1") return url;
    if (id === "bachngoclau" || id === "tieuhoadan") return url.replace(/\/$/, "") + "/page/" + page + "/";
    if (id === "otruyen") return host + "/page/" + page;
    if (id === "comonginfo") return page === "1" ? host : host + "/page/" + page + "/";
    return url.replace(/\/$/, "") + "/page/" + page + "/";
}

function parseSourceItems(doc, host, id) {
    var data = [];
    var seen = {};
    var selectors = {
        bachngoclau: "div.stories-list div.story", comong: "div.story-item-no-image", comonginfo: ".post-item",
        doctruyen: "div.story-item-no-image", doctruyenchill: "div.story-item-no-image",
        laophatgia: ".page-item-detail", metruyen: ".page-item-detail",
        mottruyen: ".story-item, .list-truyen-item-wrap", nangtho: "div.story-item-no-image",
        otruyen: "#new-story .product-grid .col-md-3", saytruyen: "div.story-item-no-image",
        tanmong: "div.story-item-no-image", tiemchungot: "div#page-moi, .book-item",
        tieuhoadan: "div.stories-list div.story", truyendexuat: ".category-grid-card-wrap, a.category-grid-card",
        truyentv: "div.story-item-no-image", vanmonglau: "a.story-card"
    };
    var selector = selectors[id] || ".story-item, .book-item, .list-truyen-item-wrap";
    var items = doc.select(selector);
    for (var i = 0; i < items.size(); i++) appendSourceItem(items.get(i), host, data, seen);
    if (!data.length) {
        var links = doc.select("a[href*='/truyen/'], a[href*='/manga/'], a[href*='manga_id='], a[href$='.html']");
        for (var j = 0; j < links.size(); j++) appendSourceItem(links.get(j), host, data, seen);
    }
    return data;
}

function appendSourceItem(item, host, data, seen) {
    var linkEl = item.select("h3 a, h6 a, a.story-name, a.d-inline-block, a.uk-position-cover, a.plain, a[href*='/truyen/'], a[href*='/manga/'], a[href*='manga_id=']").first();
    if (!linkEl) linkEl = item;
    var link = linkEl.attr("href") || "";
    if (!link || /\/chuong[-/]|\/chapter[-/]|\/doc-truyen\//i.test(link)) return;
    link = absoluteSourceUrl(host, link);
    if (/\/page\/\d+\/?(?:[?#].*)?$/i.test(link)) return;
    if (seen[link]) return;
    var image = item.select("img").first();
    var name = (linkEl.attr("aria-label") || linkEl.text()).trim();
    if (!name) { var titleEl = item.select("h3, h6, .de-cu-title, .story-item-title").first(); name = titleEl ? titleEl.text().trim() : ""; }
    if (!name && image) name = image.attr("alt") || "";
    name = String(name).replace(/\s+/g, " ").trim();
    if (!name || /^\d+$/.test(name)) return;
    var cover = image ? image.attr("data-src") || image.attr("data-original") || image.attr("src") || "" : "";
    seen[link] = true;
    data.push({ name: name, link: link, cover: cover ? absoluteSourceUrl(host, cover) : "", description: latestChapterDescription(item.select(".chapter, .chap-title, .post-on, .line, .story-item-no-image__chapters").text()), host: host });
}

function absoluteSourceUrl(host, url) {
    if (!url) return "";
    if (url.indexOf("//") === 0) return "https:" + url;
    if (url.indexOf("http") === 0) return url;
    return host + (url.charAt(0) === "/" ? url : "/" + url);
}
load("description.js");
