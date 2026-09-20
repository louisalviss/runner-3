load('config.js');
function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);

    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();

        let author = doc.select("h1.f21h em a").text();
        let name = doc.select("h1.f21h").text();
        if (author && name.indexOf(author) >= 0) name = name.replace("作者:" + author, "").replace("作者：" + author, "").replace(author, "").trim();
        let cover = doc.select(".pic em img").attr("src");
        let description = doc.select(".intro").text();
        
        // Extract details from div > a
        let detail = "";
        doc.select("div > a").forEach(e => {
            detail += e.text() + "<br>";
        });

        return Response.success({
            name: name,
            author: author,
            cover: cover,
            description: description,
            detail: detail,
            host: BASE_URL
        });
    }
    return null;
}