load('config.js');
function execute(url) {
    var response = fetch(toUrl(url));
    if (response.ok) {
        var doc = response.html();
        var novelTitle = doc.select('meta[property="og:novel:novel_name"]').attr("content");
        var author = doc.select('meta[property="og:novel:author"]').attr("content");
        var detail = doc.select(".info-meta").html();
        var cover = doc.select('meta[property="og:image"]').attr("content");
        if (!cover) {
            cover = doc.select("div.book img").attr("data-src");
        }
        if (!cover) {
            cover = doc.select("div.book img").attr("src");
        }

        return Response.success({
            name: novelTitle,
            cover: toUrl(cover),
            author: author,
            description: doc.select("div.desc-text").text(),
            detail: detail,
            host: BASE_URL
        });
    }
    return null;
}
