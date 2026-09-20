load('config.js');

function execute(url,page) {
    if(!page) page = '1';
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    url = url.replace(".html", "");
    let response = fetch(BASE_URL + url + "-" + page + ".html");
    if (response.ok) {
        let doc = response.html('gbk');
        const data = [];


        let novels = doc.select("#fengtui .bookbox");

        novels.forEach(e => {

            let novelUrl = e.select("h4 a").first().attr("href");

            let novelResponse = fetch(novelUrl);
            if (novelResponse.ok) {
                let novelDoc = novelResponse.html();


                let coverUrl = novelDoc.select(".bookcover img").first().attr("src");


                data.push({
                    name: e.select("h4 a").first().text(),
                    link: novelUrl,
                    description: e.select(".author").first().text(),
                    cover: coverUrl,
                    host: BASE_URL
                });
            }
        });
        let next = (parseInt(page) + 1).toString();
        return Response.success(data, next);
    }
    return null;
}