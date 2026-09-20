load('config.js');

function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    let response = fetch(BASE_URL + url);
    if (response.ok) {
        let doc = response.html('gbk');
        const data = [];


        let novels = doc.select("#gengxin ul li");

        novels.forEach(e => {

            let novelUrl = e.select(".s2 a").first().attr("href");

            let novelResponse = fetch(novelUrl);
            if (novelResponse.ok) {
                let novelDoc = novelResponse.html();


                let coverUrl = novelDoc.select(".bookcover img").first().attr("src");


                data.push({
                    name: e.select(".s2 a").first().text(),
                    link: novelUrl,
                    description: e.select(".s4").first().text(),
                    cover: coverUrl,
                    host: BASE_URL
                });
            }
        });

        return Response.success(data);
    }
    return null;
}