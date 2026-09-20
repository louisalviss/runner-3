function execute(input, page) {
    var host = "https://toctruyen.net";
    var url = input.indexOf("http") === 0 ? input : host + input;
    if (page && page !== "1") url += (url.indexOf("?") >= 0 ? "&" : "?") + "page=" + page;
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var data = [];
    response.html().select("#result .card-item").forEach(function(item) {
        var a = item.select("a").first();
        var name = a.select("h3.card-title").text().trim();
        var link = a.attr("href");
        var cover = item.select(".img.lazy").attr("data-original") || "";
        if (cover && cover.indexOf("http") !== 0) cover = host + cover;
        if (name && link && link.indexOf("/vo-danh") === -1) data.push({ name: name, link: link, cover: cover, description: latestChapterDescription(item.select("p.card-subtitle").text()), host: host });
    });
    return Response.success(data, data.length ? String(parseInt(page || "1", 10) + 1) : "");
}
load("description.js");
