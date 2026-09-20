load('config.js');
function execute(url) {
    url = url.replace("/info-", "/shu/").replace(".html", "/")
    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();
        let el1 = doc.select("#list dl dd a");
        const data = [];
        for (let i = 12; i < el1.size(); i++) {
            var e = el1.get(i);
            data.push({
                name: e.text(),
                url: e.attr("href"),
                host: BASE_URL
            })
        }
        return Response.success(data);
    }
    return null;
}