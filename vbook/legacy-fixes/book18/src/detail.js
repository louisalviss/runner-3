function execute(url) {
    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();
        let coverImg = doc.select("img").first().attr("src");
        if (coverImg.startsWith("/")) {
            coverImg = "https://www.book18.org" + coverImg;
        }
//body > div:nth-child(5) > div.item > div > p:nth-child(2) > span:nth-child(2)
        let author =  doc.select("div.item > div > p:nth-child(3) > a").text().replace(/作\s*者：/g, "")
        let status = doc.select("div.item > div > p:nth-child(2) > span:nth-child(1)").text()
        let novelType = doc.select("div.item > div > p:nth-child(2) > span:nth-child(2)").text()
        let charCount = doc.select("div.item > div > p:nth-child(2) > span:nth-child(3)").text()
       // let ongoing = doc.select("div > p:nth-child(4)").text()

        return Response.success({
            name: doc.select("h1").text(),
            cover: coverImg,
            author: author,
            detail: "作者: " + author,
            description: "Thể loại: " + novelType + "<br>" + "Tình trạng: " + status + "<br>" + charCount + "<br>" + "Văn án: " + "<br>" + doc.select("div.des.bb").html(),
            host: "https://www.book18.org"
        });
    }
    return null;
}