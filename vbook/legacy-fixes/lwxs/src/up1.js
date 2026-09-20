load('config.js');

function execute(url) {
    let response = fetch(BASE_URL + url);
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".r ul li").forEach(e => {
            let genre = e.select(".s1").text();
            let novelLink = e.select(".s2 a").last().attr("href");
            let novelTitle = e.select(".s2 a").last().text().replace("/","");
            let author = e.select(".s2 span").last().text();
            let date = e.select(".s5").text();
            
            let description = `[${genre}] ${author} - ${date}`;
            
            data.push({
                name: novelTitle,
                link: novelLink,
                description: description,
                host: BASE_URL
            });
        });
        return Response.success(data);
    }
    return null;
}