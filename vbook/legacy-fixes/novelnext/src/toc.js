load('config.js');
function execute(url) {
    var response = fetch(toUrl(url));
    if (response.ok) {
        var doc = response.html();
        var chapList = [];
        doc.select("#list-chapter .list-chapter li a, .list-chapter li a").forEach(function (e) {
            chapList.push({
                name: e.text(),
                url: toUrl(e.attr("href")),
                host: BASE_URL
            });
        });
        return Response.success(chapList);
    }
    return null;
}
