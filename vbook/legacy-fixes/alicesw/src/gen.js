load('config.js');
function execute(url, page) {
    if (!page) page = 1;
    let response = fetch(BASE_URL + url + "?page=" + page, {
        headers: {
            'user-agent':  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        }
    })
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".clearfix.rec_rboxone > div ul").forEach(e => {
            data.push({
                name: e.select(".two").first().text(),
                cover: "https://i.postimg.cc/T2WtdmBM/5BdXa90.webp",
                link: e.select(".two a").attr("href"),
                description: e.select(".four").first().text(),
                host: BASE_URL
            })
        });
        let next = parseInt(page) + 1;
        return Response.success(data, next)
    }
    return null;
}