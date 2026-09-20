load('config.js');
function execute(url, page) {
    if (!page) {
        page = '1';
    }
    var pageUrl = toUrl(url);
    if (page && String(page) !== '1') {
        pageUrl = pageUrl + (pageUrl.indexOf('?') >= 0 ? '&' : '?') + 'page=' + page;
    }
    var response = fetch(pageUrl);
    if (response.ok) {
        var doc = response.html();
        var novelList = [];
        var next = '';
        var nextElement = doc.select(".pagination > li.active + li").last().select('a');
        if (nextElement.size() > 0) {
            var nextPageLink = nextElement.attr('href');
            var match = nextPageLink.match(/page=(\d+)/);
            if (match && match[1]) {
                next = match[1];
            }
        }
        doc.select("#list-page .col-novel-main .list-novel > .row, .col-novel-main .list-novel > .row").forEach(function (e) {
            var cover = e.select(".cover").first().attr("data-src");
            if (!cover) {
                cover = e.select(".cover").first().attr("src");
            }
            novelList.push({
                name: e.select(".novel-title a").text(),
                link: toUrl(e.select(".novel-title a").first().attr("href")),
                description: e.select(".author").text(),
                cover: toUrl(cover),
                host: BASE_URL,
            });
        });
        // Check if there's only one page
        if (next === '1' || next === '0') {
            next = ''; // Set next to empty to indicate no more pages
        }
        return Response.success(novelList, next);
    }
    return null;
}
