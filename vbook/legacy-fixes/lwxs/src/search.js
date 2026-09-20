load('config.js');
function execute(key) {
    key = String(key || '');
    var response = fetch(BASE_URL + "/search.html", {
        method: "POST",
        headers: {"Content-Type":"application/x-www-form-urlencoded","Referer":BASE_URL+"/","User-Agent":"Mozilla/5.0"},
        body: "searchkey=" + encodeURIComponent(key) + "&searchtype=all"
    });
    if (!response.ok) return Response.error("SEARCH_HTTP_" + response.status);
    var doc = response.html();
    var books = [];
    doc.select("#alistbox > div").forEach(function(e) {
        var linkEl = e.select(".pic a").first();
        var novelLink = linkEl.attr("href") || "";
        var img = e.select(".pic a img").first();
        var novelTitle = (img ? img.attr("alt") : "") || e.select(".title a").first().text();
        if (!novelLink || !novelTitle) return;
        var author = e.select(".title span").text().replace("作者：", "");
        var chapterTitle = e.select(".sys li a").text();
        var cover = img ? img.attr("src") : "";
        books.push({name:novelTitle,link:novelLink,cover:cover,description:author + " - " + chapterTitle,host:BASE_URL});
    });
    return Response.success(books);
}
