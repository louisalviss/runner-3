var SEARCH_BATCH_SIZE = 5;

function execute(key, page) {
    key = String(key || "");
    try { if (key.normalize) key = key.normalize("NFC"); } catch (e) {}
    var batch = parseInt(page || "1", 10) - 1;
    if (isNaN(batch) || batch < 0) batch = 0;
    var sources = [
        { name: "Nguyệt Mộng", run: searchNguyetMong },
        { name: "Toctruyen", run: searchTocTruyen },
        { name: "Yêu Truyện", run: searchYeuTruyen },
        { name: "Nguyệt Lâu", run: searchNguyetLau },
        { name: "Bạch Ngọc Lâu", id: "bachngoclau" },
        { name: "Cổ Mộng", id: "comong" },
        { name: "Cổ Mộng Info", id: "comonginfo" },
        { name: "Đọc Truyện", id: "doctruyen" },
        { name: "Đọc Truyện Chill", id: "doctruyenchill" },
        { name: "Lão Phật Gia", id: "laophatgia" },
        { name: "Mê Truyện", id: "metruyen" },
        { name: "MonkeyD", id: "monkeyd" },
        { name: "Mọt Truyện", id: "mottruyen" },
        { name: "Nàng Thơ", id: "nangtho" },
        { name: "Ổ Của Dưa", id: "ocuadua" },
        { name: "Ổ Truyện", id: "otruyen" },
        { name: "Say Truyện", id: "saytruyen" },
        { name: "Tản Mộng", id: "tanmong" },
        { name: "Tiệm Chữ Ngọt", id: "tiemchungot" },
        { name: "Tiểu Hoa Đán", id: "tieuhoadan" },
        { name: "Truyện Đề Xuất", id: "truyendexuat" },
        { name: "Truyện TV", id: "truyentv" },
        { name: "Vân Mộng Lâu", id: "vanmonglau" },
        { name: "Vivu Truyện NET", id: "vivutruyen" }
    ];
    var start = batch * SEARCH_BATCH_SIZE;
    var end = Math.min(start + SEARCH_BATCH_SIZE, sources.length);
    var data = [];
    for (var i = start; i < end; i++) {
        try {
            var items = sources[i].run ? sources[i].run(key) || [] : searchAdditional(sources[i].id, key);
            for (var j = 0; j < items.length; j++) {
                items[j].name = "[" + sources[i].name + "] " + items[j].name;
                data.push(items[j]);
            }
        } catch (error) {
            Log.log("Search " + sources[i].name + " lỗi: " + error);
        }
    }
    var next = end < sources.length ? String(batch + 2) : "";
    return Response.success(data, next);
}

function searchAdditional(id, key) {
    if (id === "ocuadua") return searchOCuaDua(key);
    var hosts = {
        bachngoclau: "https://bachngoclau.com", comong: "https://comong.site", comonginfo: "https://comong.info", doctruyen: "https://doctruyen.shop",
        doctruyenchill: "https://www.doctruyenchill.net", laophatgia: "https://laophatgia.fit", metruyen: "https://metruyen.fit",
        monkeyd: "https://www.monkeydd.com", mottruyen: "https://mottruyen.top", nangtho: "https://nangtho.site",
        otruyen: "https://otruyen.online", saytruyen: "https://saytruyen.vn", tanmong: "https://yeungontinh.site",
        tiemchungot: "https://tiemchungot.com", tieuhoadan: "https://tieuhoadan.com", truyendexuat: "https://truyendexuat.com",
        truyentv: "https://truyentv.site", vanmonglau: "https://vanmonglau.com", vivutruyen: "https://vivutruyen.net"
    };
    var host = hosts[id];
    var encoded = encodeURIComponent(key);
    var url = host + "/tim-kiem?key_word=" + encoded + "&page=1";
    if (id === "bachngoclau" || id === "tieuhoadan") url = host + "/?s=" + encoded + "&page=1";
    if (id === "comonginfo") url = host + "/?s=" + encoded + "&paged=1";
    if (id === "laophatgia" || id === "metruyen") url = host + "/?s=" + encoded + "&post_type=wp-manga";
    if (id === "monkeyd") url = host + "/tim-kiem?search=" + encoded + "&page=1";
    if (id === "mottruyen") url = host + "/tim-kiem?keyword=" + encoded;
    if (id === "tiemchungot") url = host + "/kham-pha?q=" + encoded;
    if (id === "truyendexuat") url = host + "/search/" + encoded + "/";
    if (id === "vanmonglau") url = host + "/search.php?q=" + encoded + "&page=1";
    var response = fetch(url, { headers: { "referer": host + "/", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return [];
    return parseAdditionalSearch(response.html(), host);
}

function parseAdditionalSearch(doc, host) {
    var data = [];
    var seen = {};
    var items = doc.select(".stories-list .story, .story-item-no-image, .page-item-detail, .product-grid .card, .search-result-item, article.post, .post-item, .category-grid-card-wrap, a.category-grid-card, a.story-card, .book-item, .story-item, .list-truyen-item-wrap");
    for (var i = 0; i < items.size(); i++) {
        var item = items.get(i);
        var linkEl = item.select("h3 a, h6 a, a.story-name, a.uk-position-cover, a.plain, a[href*='/truyen/'], a[href*='/manga/'], a[href$='.html'], a[href*='manga_id=']").first();
        if (!linkEl) linkEl = item;
        var link = linkEl.attr("href") || "";
        if (!link || /\/chuong[-/]|\/chapter[-/]|\/doc-truyen\//i.test(link)) continue;
        if (link.indexOf("http") !== 0) link = host + (link.charAt(0) === "/" ? link : "/" + link);
        if (seen[link]) continue;
        var image = item.select("img").first();
        var name = (linkEl.attr("aria-label") || linkEl.text()).trim() || item.select("h3, h6, .story-title").text().trim() || (image ? image.attr("alt") || "" : "");
        if (!name) continue;
        var cover = image ? image.attr("data-src") || image.attr("data-original") || image.attr("src") || "" : "";
        if (cover && cover.indexOf("http") !== 0) cover = host + (cover.charAt(0) === "/" ? cover : "/" + cover);
        seen[link] = true;
        data.push({ name: name.replace(/\s+/g, " ").trim(), link: link, cover: cover, host: host });
    }
    return data;
}

function searchOCuaDua(key) {
    var response = fetch("https://doctruyen-be-ojbd.onrender.com/api/story?search=" + encodeURIComponent(key) + "&page=1&limit=20", { headers: { "accept": "application/json" } });
    if (!response.ok) return [];
    var items = response.json().data || [];
    var data = [];
    for (var i = 0; i < items.length; i++) data.push({ name: items[i].title || "", link: "https://ocuadua.com/story/" + (items[i].slug || items[i]._id), cover: items[i].coverImage || "", host: "https://ocuadua.com" });
    return data;
}

function searchNguyetMong(key) {
    var response = fetch("https://nguyetmongthu.com/?post_type=truyen&s=" + encodeURIComponent(key));
    if (!response.ok) return [];
    var data = [];
    response.html().select(".truyen-grid article.truyen").forEach(function(item) {
        var link = item.select("h3.truyen-title a").first();
        if (link) data.push({ name: link.text().trim(), link: link.attr("href"), cover: item.select("img").attr("src") || "", host: "https://nguyetmongthu.com" });
    });
    return data;
}

function searchTocTruyen(key) {
    var response = fetch("https://toctruyen.net/content/navSearch?kw=" + encodeURIComponent(key), { headers: { "x-requested-with": "XMLHttpRequest", "referer": "https://toctruyen.net/tim-kiem" } });
    if (!response.ok) return [];
    var items = response.json().items || [];
    var data = [];
    for (var i = 0; i < items.length; i++) {
        var html = items[i];
        var href = html.match(/href="([^"]+)"/);
        var name = html.match(/<div class="mb-1">([\s\S]*?)<\/div>/);
        if (!href || !name) continue;
        var link = href[1];
        if (link.indexOf("http") !== 0) link = "https://toctruyen.net" + link;
        var image = html.match(/data-original="([^"]+)"/);
        var cover = image ? image[1] : "";
        if (cover && cover.indexOf("http") !== 0) cover = "https://toctruyen.net" + cover;
        data.push({ name: name[1].replace(/<[^>]+>/g, "").trim(), link: link, cover: cover, host: "https://toctruyen.net" });
    }
    return data;
}

function searchYeuTruyen(key) {
    var response = fetch("https://yeutruyen.me/?s=" + encodeURIComponent(key), { headers: { "referer": "https://yeutruyen.me/" } });
    if (!response.ok) return [];
    var data = [];
    var items = response.html().select(".page-content article.post");
    for (var i = 0; i < items.size(); i++) {
        var item = items.get(i);
        var image = item.select("img.slider-image");
        var link = item.select("a.uk-position-cover").attr("href") || "";
        if (link) data.push({ name: (image.attr("alt") || "").trim(), link: link, cover: image.attr("data-src") || image.attr("src") || "", description: item.select(".chap-title").text().trim(), host: "https://yeutruyen.me" });
    }
    return data;
}

function searchNguyetLau(key) {
    var page = fetchNguyetLauSearch("/novels?search=" + encodeURIComponent(key));
    if (!page || !page.props || !page.props.novels) return [];
    var items = page.props.novels.data || [];
    var data = [];
    for (var i = 0; i < items.length; i++) {
        var item = items[i] && items[i].data ? items[i].data : items[i];
        if (!item) continue;
        var cover = item.cover_image || "";
        if (cover && cover.indexOf("http") !== 0) cover = "https://nguyetlau.top/storage/" + cover.replace(/^\//, "");
        data.push({ name: item.title || "", link: "https://nguyetlau.top/novels/" + item.slug, cover: cover, host: "https://nguyetlau.top" });
    }
    return data;
}

function fetchNguyetLauSearch(path) {
    var response = fetch("https://nguyetlau.top" + path, { headers: { "Accept": "text/html", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return null;
    var raw = response.html().select("div#app").attr("data-page");
    if (!raw) return null;
    raw = String(raw).replace(/&quot;/g, '"').replace(/&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    try { return JSON.parse(raw); } catch (error) { return null; }
}
