function execute() {
    var result = [];
    collectGenres("https://nguyetmongthu.com", "Nguyệt Mộng", "gen_nguyetmongthu.js", result);
    collectGenres("https://toctruyen.net", "Toctruyen", "gen_toctruyen.js", result);
    collectYeuGenres(result);
    collectNguyetLauGenres(result);
    collectDaoTruyenGenres(result);
    appendRemainingGenreRoots(result);
    return Response.success(result);
}

function collectDaoTruyenGenres(result) {
    var response = fetch("https://daotruyen.me/api/public/categories", { headers: { "accept": "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 Chrome/119.0.0.0", "referer": "https://daotruyen.me/", "origin": "https://daotruyen.me" } });
    if (!response.ok) return;
    var items = response.json() || [];
    for (var i = 0; i < items.length; i++) {
        if (items[i].id && items[i].categoryName) result.push({ title: "[Đảo Truyện] " + items[i].categoryName, input: "/api/public/v2/stories-by-category/" + items[i].id + "?pageNo=0&pageSize=20", script: "gen_daotruyen.js" });
    }
}

function appendRemainingGenreRoots(result) {
    var sources = [
        ["Bạch Ngọc Lâu", "bachngoclau|/truyen/", "gen_other.js"], ["Cổ Mộng", "comong|https://comong.site", "gen_other.js"],
        ["Cổ Mộng Info", "comonginfo|https://comong.info", "gen_other.js"],
        ["Đảo Truyện", "/api/public/stories", "gen_daotruyen.js"], ["Đọc Truyện", "doctruyen|https://doctruyen.shop", "gen_other.js"],
        ["Đọc Truyện Chill", "doctruyenchill|https://www.doctruyenchill.net", "gen_other.js"], ["Lão Phật Gia", "laophatgia|/", "gen_other.js"],
        ["Mê Truyện", "metruyen|/", "gen_other.js"], ["MonkeyD", "truyen-moi", "gen_monkeyd.js"],
        ["Mọt Truyện", "mottruyen|https://mottruyen.top/danh-sach/truyen-moi", "gen_other.js"], ["Nàng Thơ", "nangtho|https://nangtho.site", "gen_other.js"],
        ["Ổ Của Dưa", "https://doctruyen-be-ojbd.onrender.com/api/story?filter=popular&page=1&limit=20", "gen_ocuadua.js"],
        ["Ổ Truyện", "otruyen|/", "gen_other.js"], ["Say Truyện", "saytruyen|https://saytruyen.vn", "gen_other.js"],
        ["Tản Mộng", "tanmong|https://yeungontinh.site", "gen_other.js"], ["Tiệm Chữ Ngọt", "tiemchungot|https://tiemchungot.com/kham-pha", "gen_other.js"],
        ["Tiểu Hoa Đán", "tieuhoadan|/truyen/", "gen_other.js"], ["Truyện Đề Xuất", "truyendexuat|https://truyendexuat.com/moi-cap-nhat/", "gen_other.js"],
        ["Truyện TV", "truyentv|https://truyentv.site", "gen_other.js"], ["Vân Mộng Lâu", "vanmonglau|/danh-sach-truyen/", "gen_other.js"],
        ["Vivu Truyện NET", "/moi-cap-nhat/", "gen_vivutruyen_net.js"]
    ];
    for (var i = 0; i < sources.length; i++) result.push({ title: "[" + sources[i][0] + "] Tất cả", input: sources[i][1], script: sources[i][2] });
}

function collectYeuGenres(result) {
    var response = fetch("https://yeutruyen.me");
    if (!response.ok) return;
    var seen = {};
    response.html().select("ul.danh-muc li.cat-item a.menu-item").forEach(function(item) {
        var title = item.text().trim();
        var href = item.attr("href");
        if (!title || !href || seen[href]) return;
        seen[href] = true;
        if (href.indexOf("http") !== 0) href = "https://yeutruyen.me" + href;
        result.push({ title: "[Yêu Truyện] " + title, input: href, script: "gen_yeutruyen.js" });
    });
}

function collectNguyetLauGenres(result) {
    var response = fetch("https://nguyetlau.top/novels", { headers: { "Accept": "text/html", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return;
    var raw = response.html().select("div#app").attr("data-page");
    if (!raw) return;
    raw = String(raw).replace(/&quot;/g, '"').replace(/&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    try {
        var page = JSON.parse(raw);
        var items = page.props && page.props.categories && page.props.categories.data ? page.props.categories.data : [];
        for (var i = 0; i < items.length; i++) result.push({ title: "[Nguyệt Lâu] " + items[i].name, input: "/novels?category=" + items[i].slug, script: "gen_nguyetlau.js" });
    } catch (error) {}
}

function collectGenres(url, sourceName, script, result) {
    var response = fetch(url);
    if (!response.ok) return;
    var host = url.match(/^https?:\/\/[^/]+/)[0];
    var seen = {};
    response.html().select('a[href*="/the-loai/"], a[href*="tim-kiem.html?genre"]').forEach(function(item) {
        var title = item.text().trim();
        var href = item.attr("href");
        if (!title || !href) return;
        if (/^xem (tất cả|thêm)/i.test(title)) return;
        if (href.indexOf("http") !== 0) href = host + (href.charAt(0) === "/" ? href : "/" + href);
        var key = sourceName + "|" + title;
        if (!seen[key]) {
            seen[key] = true;
            result.push({ title: "[" + sourceName + "] " + title, input: href, script: script });
        }
    });
}
