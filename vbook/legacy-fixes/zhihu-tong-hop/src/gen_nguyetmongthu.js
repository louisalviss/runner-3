function execute(input, page) {
    var host = "https://nguyetmongthu.com";
    var url = input.indexOf("http") === 0 ? input : host + input;
    if (page && page !== "1") url = url.replace(/\/$/, "") + "/page/" + page + "/";
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var data = [];
    response.html().select('a[href*="/truyen/"]').forEach(function(item) {
        var name = item.select("h3").text().trim();
        var link = item.attr("href");
        if (name && link) data.push({ name: name, link: link, cover: item.select("img").attr("src") || "", description: latestChapterDescription(item.select("span").text()), host: host });
    });
    return Response.success(data, data.length ? String(parseInt(page || "1", 10) + 1) : "");
}
load("description.js");
