load('config.js');

function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    var response = fetch(url);
    if (response.ok) {
        var doc = response.html();
        
        var nameEl = doc.select("h1").first();
        var name = nameEl ? nameEl.text() + "" : "";
        
        var authorEl = doc.select("a[href*='/tac-gia/']").first();
        var author = authorEl ? authorEl.text() + "" : "";
        
        var coverEl = doc.select(".summary img, .info img, .row img, .book img, .thumb img, article img").first();
        var cover = coverEl ? coverEl.attr("src") + "" : "";
        
        var descEl = doc.select(".summary, .description, #summary, .desc, .entry-content, .info-desc").first();
        var description = descEl ? descEl.html() + "" : "";
        
        var bodyText = doc.select("body").text() + "";
        var ongoing = bodyText.indexOf("Đang") >= 0;

        var genres = [];
        doc.select('a[href*="/the-loai/"]').forEach(function(el) {
            genres.push({
                title: el.text() + "",
                input: (el.attr('href') || "") + "",
                script: 'gen.js'
            });
        });

        return Response.success({
            name: name,
            cover: cover,
            author: author,
            description: description,
            ongoing: ongoing,
            host: BASE_URL,
            genres: genres
        });
    }
    return Response.error('Failed to load detail');
}
