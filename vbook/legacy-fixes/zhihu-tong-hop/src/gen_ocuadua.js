function execute(url, page) {
    if (page) url = String(url).replace(/([?&]page=)\d+/, "$1" + page);
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var items = json.data || json.items || json.stories || [];
    var data = [];
    var seen = {};
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var slug = item.slug || item._id || item.id;
        var link = "https://ocuadua.com/story/" + slug;
        if (!slug || seen[link]) continue;
        seen[link] = true;
        var cover = item.coverImage || item.cover || "";
        if (cover && cover.indexOf("http") !== 0) cover = "https://ocuadua.com" + cover;
        data.push({ name: item.title || item.name || "Không tên", link: link, cover: cover, description: latestChapterDescription(item.description || item.intro), host: "https://ocuadua.com" });
    }
    var next = json.pagination && json.pagination.page < json.pagination.totalPages ? String(json.pagination.page + 1) : "";
    return Response.success(data, next);
}
load("description.js");
