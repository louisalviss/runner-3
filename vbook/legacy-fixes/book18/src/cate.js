load('config.js');
function execute(url,page) {
    if(!page) page = '1';
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    let response = fetch(BASE_URL + url + "?page=" + page + "&per-page=100");
    console.log(BASE_URL + url + "?page=" + page + "&per-page=100")
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".col-md-6 ul li").forEach(e => {
          data.push({
            name: e.select("a").first().text(),
            link: BASE_URL + e.select("a").first().attr("href"),
            description: e.select("a").first().text(),
            host: BASE_URL
          })
        });
        let next = (parseInt(page) + 1).toString();
        return Response.success(data,next)
    }
    return null;
}