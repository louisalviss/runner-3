load('config.js');

function execute(url) {
    let response = fetch(BASE_URL + url);
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".GARAN .top").forEach(e => {
            let novelLink = e.select("dl dt a").first().attr("href");
            let novelTitle = e.select("dl dt a").text();
            let author = e.select("dl dt").last().text().split(" / ")[1].replace("èï¼","");
            let description = e.select("dl dd").text();
            
            data.push({
                name: novelTitle,
                link: novelLink,
                description: `[${author}] ${description}`,
                host: BASE_URL
            });
        });
        return Response.success(data);
    }
    return null;
}