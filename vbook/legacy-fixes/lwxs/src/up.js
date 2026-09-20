load('config.js');

function execute(url) {
    let response = fetch(BASE_URL + url);
    if (response.ok) {
        let doc = response.html();
        const data = [];
        doc.select(".l ul li").forEach(e => {
            let genre = e.select(".s1").text();
            let novelLink = e.select(".s2 a").last().attr("href");
            let novelTitle = e.select(".s2 a").last().text();
            let chapterTitle = e.select(".s3 a").first().text();
            let author = e.select(".s4").text();
            let date = e.select(".s5").text();

            // ThÃªm Äoáº¡n láº¥y áº£nh cover dá»±a trÃªn ÄÆ°á»ng link cá»§a truyá»n
            let coverMatch = novelLink.match(/(\d+)\/?$/);
            let coverId = coverMatch ? coverMatch[1] : null;
            let coverUrl = coverId ? `https://img.lwxs.com/${coverId}/${coverId}.jpg` : null;

            let description = `${genre} - ${date} - ${author}`;

            data.push({
                name: novelTitle,
                link: novelLink,
                description: description,
                cover: coverUrl, // ThÃªm trÆ°á»ng cover vÃ o dá»¯ liá»u
                host: BASE_URL
            });
        });
        return Response.success(data);
    }
    return null;
}