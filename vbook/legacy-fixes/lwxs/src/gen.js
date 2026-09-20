load('config.js');

function execute(url, page) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    if (!page) page = '1';
    
    let response = fetch(BASE_URL + url + page + ".html");
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select("#alistbox > div").forEach(e => {
            let novelLink = e.select(".pic a").attr("href");
            let novelTitle = e.select(".pic a img").attr("alt");
            let author = e.select(".title span").text().replace("作者：", "");
            let chapterTitle = e.select(".sys li a").text();
            let cover = e.select(".pic img").attr("src");
            
            let description = `${author} - ${chapterTitle}`;
            
            data.push({
                name: novelTitle,
                link: novelLink,
                cover: cover,
                description: description,
                host: BASE_URL
            });
        });

        let next = (parseInt(page) + 1).toString();
        return Response.success(data, next);
    }
    return null;
}
