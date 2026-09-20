function execute(url) {
    if (url.indexOf("daotruyen.me") >= 0) return tocDaoTruyen(url);
    if (url.indexOf("ocuadua.com") >= 0) return tocOCuaDua(url);
    if (url.indexOf("nguyetmongthu.com") >= 0) return tocNguyetMong(url);
    if (url.indexOf("toctruyen.net") >= 0) return tocTocTruyen(url);
    if (url.indexOf("yeutruyen.me") >= 0) return tocYeuTruyen(url);
    if (url.indexOf("nguyetlau.top") >= 0) return tocNguyetLau(url);
    return tocGeneric(url);
}

function tocGeneric(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var host = (String(url).match(/^https?:\/\/[^/]+/) || [""])[0];
    var list = [];
    var seen = {};
    var selector = ".chapter-list-container .chapter-item a, .story-chapters-list a, div.story-detail__list-chapter--list ul li a, div.page-content-listing.single-page ul li a, .listing-chapters_wrap li a, .list-chapters .episode-title a, a[href^='/doc-truyen/'], #listChapters .item .episode-title a, .chapter-scroll a.chapter-row, .chapter-grid a.chapter-item, .chapter-list .chapter-item a, #chapterList a, div.list a.chap-title";
    response.html().select(selector).forEach(function(item) {
        var href = item.attr("href") || "";
        if (!href || seen[href]) return;
        if (href.indexOf("http") !== 0) href = host + (href.charAt(0) === "/" ? href : "/" + href);
        seen[href] = true;
        var name = item.select(".chapter-name, .chapter-item-name, h3").text().trim() || item.text().trim();
        list.push({ name: cleanObfuscatedText(name || "Chương " + (list.length + 1)), url: href, host: host });
    });
    return Response.success(list);
}

function tocDaoTruyen(url) {
    var response = fetch(url, { headers: daoHeaders() });
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var chapters = json.chapters || [];
    var story = json.story || {};
    var slug = story.url || story.slug || "";
    var list = [];
    for (var i = 0; i < chapters.length; i++) {
        var number = chapters[i].chapterNumber || 0;
        var title = chapters[i].title;
        list.push({ name: title ? "Chương " + number + " - " + title : "Chương " + number, url: "https://daotruyen.me/api/public/v2/" + slug + "/" + number, host: "https://daotruyen.me" });
    }
    return Response.success(list);
}

function tocOCuaDua(url) {
    var match = String(url).match(/\/story\/([A-Za-z0-9-]+)/);
    if (!match) return Response.error("URL không hợp lệ");
    var response = fetch("https://doctruyen-be-ojbd.onrender.com/api/story/" + match[1]);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var item = response.json();
    item = item.data || item;
    var chapters = item.chapters || [];
    var list = [];
    for (var i = 0; i < chapters.length; i++) {
        var chapter = chapters[i];
        var id = typeof chapter === "string" ? chapter : chapter._id || chapter.id;
        list.push({ name: chapter.title || chapter.name || "Chương " + (i + 1), url: "https://ocuadua.com/story/" + (item.slug || match[1]) + "/read?chapter=" + id, host: "https://ocuadua.com" });
    }
    return Response.success(list);
}

function daoHeaders() {
    return { "accept": "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36", "referer": "https://daotruyen.me/", "origin": "https://daotruyen.me" };
}

function cleanObfuscatedText(value) {
    var text = String(value || "");
    var previous = "";
    while (text !== previous) {
        previous = text;
        text = text.replace(/([0-9A-Za-zÀ-ỹĐđ])\s*\/{1,}\s*([0-9A-Za-zÀ-ỹĐđ])/g, "$1$2");
    }
    return text.replace(/\s{2,}/g, " ").trim();
}

function tocYeuTruyen(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var list = [];
    response.html().select("a.chap-title").forEach(function(item) { list.push({ name: item.text().trim(), url: item.attr("href"), host: "https://yeutruyen.me" }); });
    list.reverse();
    return Response.success(list);
}

function tocNguyetLau(url) {
    var page = fetchNguyetLauPage(url);
    if (!page || !page.props) return Response.error("Không đọc được Nguyệt Lâu");
    var novel = page.props.novel && page.props.novel.data ? page.props.novel.data : page.props.novel;
    var slug = novel && novel.slug ? novel.slug : (url.match(/\/novels\/([^/]+)/) || ["", ""])[1];
    var items = page.props.chapters && page.props.chapters.data ? page.props.chapters.data : (novel && novel.chapters ? novel.chapters : []);
    var list = [];
    for (var i = 0; i < items.length; i++) {
        var item = items[i] && items[i].data ? items[i].data : items[i];
        var number = item && (item.chapter_number || item.number || item.id);
        if (number) list.push({ name: item.title || "Chương " + number, url: "https://nguyetlau.top/novels/" + slug + "/chapter/" + number, host: "https://nguyetlau.top" });
    }
    return Response.success(list);
}

function fetchNguyetLauPage(url) {
    var response = fetch(url, { headers: { "Accept": "text/html", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return null;
    var raw = response.html().select("div#app").attr("data-page");
    if (!raw) return null;
    raw = String(raw).replace(/&quot;/g, '"').replace(/&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    try { return JSON.parse(raw); } catch (error) { return null; }
}

function tocNguyetMong(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var list = [];
    var seen = {};
    response.html().select('a[href*="/truyen/"][href*="/chuong-"]').forEach(function(item) {
        var href = item.attr("href");
        var match = href.match(/\/chuong-(\d+)\/?$/i);
        if (href && match && !seen[href]) { seen[href] = true; list.push({ name: "Chương " + match[1], url: href, host: "https://nguyetmongthu.com" }); }
    });
    return Response.success(list);
}

function tocTocTruyen(url) {
    var match = url.match(/\/truyen\/([^/]+)/);
    if (!match) return Response.error("URL không hợp lệ");
    var response = fetch("https://toctruyen.net/content/subitems?pid=" + match[1]);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var items = json.data && json.data.e;
    var list = [];
    if (!items) return Response.success(list);
    for (var i = items.length - 1; i >= 0; i--) {
        var item = items[i];
        var href = item[3].indexOf("http") === 0 ? item[3] : "https://toctruyen.net" + item[3];
        list.push({ name: item[2], url: href, host: "https://toctruyen.net" });
    }
    return Response.success(list);
}
