function execute(path) {
    var page = fetchNguyetLau(path || "/novels?sort=latest_chapter");
    if (!page || !page.props || !page.props.novels) return Response.error("Không đọc được Nguyệt Lâu");
    var items = page.props.novels.data || [];
    var data = [];
    for (var i = 0; i < items.length; i++) {
        var item = items[i] && items[i].data ? items[i].data : items[i];
        if (!item) continue;
        var cover = item.cover_image || "";
        if (cover && cover.indexOf("http") !== 0) cover = "https://nguyetlau.top/storage/" + cover.replace(/^\//, "");
        data.push({ name: item.title || "", link: "https://nguyetlau.top/novels/" + item.slug, cover: cover, description: "", host: "https://nguyetlau.top" });
    }
    var next = page.props.novels.next_page_url || "";
    if (next.indexOf("https://nguyetlau.top") === 0) next = next.substring(22);
    return Response.success(data, next);
}

function fetchNguyetLau(path) {
    var url = path.indexOf("http") === 0 ? path : "https://nguyetlau.top" + path;
    var response = fetch(url, { headers: { "Accept": "text/html", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return null;
    var raw = response.html().select("div#app").attr("data-page");
    if (!raw) return null;
    raw = String(raw).replace(/&quot;/g, '"').replace(/&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    try { return JSON.parse(raw); } catch (error) { return null; }
}
