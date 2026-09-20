function execute(url, page) {
    page = page ? String(page) : "1";
    var fullUrl = url;
    if (page !== "1") fullUrl = url.replace(/\/$/, "") + "/page/" + page + "/";
    var response = fetch(fullUrl);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var data = [];
    var items = doc.select(".page-content .uk-cover-container");
    for (var i = 0; i < items.size(); i++) {
        var item = items.get(i);
        var image = item.select("img.slider-image");
        var link = item.select("a.uk-position-cover").attr("href") + "";
        var cover = image.attr("data-src") + "" || image.attr("src") + "";
        if (link && link.indexOf("http") !== 0) link = "https://yeutruyen.me" + link;
        if (cover && cover.indexOf("http") !== 0) cover = "https://yeutruyen.me" + cover;
        var name = (image.attr("alt") + "").trim() || item.select(".de-cu-title").text().trim();
        if (link) data.push({ name: name, link: link, cover: cover, description: latestChapterDescription(item.select(".chap-title").text()), host: "https://yeutruyen.me" });
    }
    var next = doc.select('a[data-page="' + (parseInt(page, 10) + 1) + '"]').size() > 0 ? String(parseInt(page, 10) + 1) : "";
    return Response.success(data, next);
}
load("description.js");
