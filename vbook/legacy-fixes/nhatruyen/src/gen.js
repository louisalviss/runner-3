load('config.js');

function execute(url, page) {
    if (!page) page = '1';
    var fetchUrl = url;
    if (page !== '1') {
        fetchUrl = url.replace(/\/$/, '') + '/page/' + page + '/';
    }

    var response = fetch(fetchUrl);
    if (response.ok) {
        var doc = response.html();
        var books = [];
        doc.select('.nt-grid-item, .nt-story-item, .manga-item, .item-manga, .item').forEach(function(el) {
            var nameEl = el.select('h3.nt-grid-title, h3.nt-story-title, h2.entry-title a, h3.nt-title a, .title a, a[href*="/truyen/"], a').first();
            var selfHref = el.attr('href') + "";
            var linkEl = selfHref && selfHref.indexOf('http') > -1 ? el : el.select('a[href*="/truyen/"], a').first();
            var coverEl = el.select('img').first();
            if (nameEl && linkEl) {
                var link = linkEl.attr('href') + "";
                if (link && !link.includes("javascript:")) {
                    if (!link.startsWith("http")) link = BASE_URL + (link.startsWith("/") ? "" : "/") + link;
                    
                    var cover = "";
                    if (coverEl) {
                        cover = coverEl.attr('data-src') || coverEl.attr('src') || "";
                        if (cover && cover.startsWith("//")) cover = "https:" + cover;
                    }

                    books.push({
                        name: nameEl.text().trim(),
                        link: link,
                        cover: cover,
                        description: el.select('.entry-summary, .nt-desc-short, .chapter').text().trim(),
                        host: BASE_URL
                    });
                }
            }
        });

        // Deduplicate
        var uniqueBooks = [];
        var seenUrls = {};
        for (var i = 0; i < books.length; i++) {
            var b = books[i];
            if (!seenUrls[b.link]) {
                seenUrls[b.link] = true;
                uniqueBooks.push(b);
            }
        }

        var next = doc.select('.page-numbers.next').size() > 0;
        return Response.success(uniqueBooks, next ? String(parseInt(page) + 1) : null);
    }
    return Response.error('Failed to load book list');
}
