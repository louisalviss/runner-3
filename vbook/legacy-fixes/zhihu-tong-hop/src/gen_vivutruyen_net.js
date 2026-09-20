function execute(path) {
    var response = fetch("https://vivutruyen.net" + path);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var data = [];
    response.html().select("div#page-moi").forEach(function(item) {
        var title = item.select("h3.de-cu-title").first();
        var link = item.select("a.uk-position-cover").first();
        var image = item.select("img").first();
        var chapter = item.select("div.chap-title span span").first();
        var chapterText = chapter ? chapter.text().trim() : "";
        var name = title ? title.text().trim().replace(chapterText, "").trim() : "";
        if (name && link) data.push({ name: name, link: link.attr("href"), cover: image ? image.attr("data-src") || "" : "", description: latestChapterDescription(chapterText), host: "https://vivutruyen.net" });
    });
    return Response.success(data);
}
load("description.js");
