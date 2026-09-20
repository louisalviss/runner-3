load('config.js');
function execute(url) {
    let response = fetch(BASE_URL + url, {
        headers: {
            'user-agent':  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        }
    });
    
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".clearfix.rec_rboxone > div ul").forEach(e => {
            data.push({
                name: e.select(".two").first().text(),
                cover: "https://i.postimg.cc/T2WtdmBM/5BdXa90.webp",
                link: e.select(".two a").attr("href"),
                description: e.select(".sev").first().text() + " " + e.select(".five").first().text(),
                host: BASE_URL
            })
        });
        return Response.success(data)
    }
    return null;
}