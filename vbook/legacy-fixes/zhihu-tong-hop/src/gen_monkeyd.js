function execute(path, page) {
    page = page || "1";
    var response = fetch("https://www.monkeydd.com/" + path + ".html?page=" + page);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var data = [];
    response.html().select(".product-grid .card").forEach(function(item) {
        var link = item.select("a").first();
        var image = item.select("a img").last();
        data.push({ name: item.select("a h3").first().text().trim(), link: link.attr("href"), cover: image.attr("data-src") || "", description: latestChapterDescription(item.select(".post-on").first().text()), host: "https://www.monkeydd.com" });
    });
    return Response.success(data, data.length ? String(parseInt(page, 10) + 1) : "");
}
load("description.js");
