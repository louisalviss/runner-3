load('config.js');
function execute(url) {
    let response = fetch(url, {
        headers: {
            "user-agent": UserAgent.chrome()        // Đặt user agent trong header - Thêm vào request header
        }
    });
    if (response.ok) {
        let doc = response.html();
        // console.log(doc);
        var genres = [];
        // Lấy thể loại chính từ dòng "Phân loại"
        doc.select(".novel_info p:nth-child(2) a").forEach(e => {
            genres.push({
                title: e.text(),
                input: BASE_URL + e.attr("href"),
                script: "suggest1.js"
            });
        });

        // Lấy thêm các thẻ (tags) ở phía dưới
        doc.select(".tags_list a").forEach(e => {
            genres.push({
                title: e.text().replace("#", ""), // Loại bỏ dấu # nếu có
                input: BASE_URL + e.attr("href"),
                script: "suggest1.js"
            });
        });

        // Lấy tên tác giả từ dòng đầu tiên trong novel_info
        let author = doc.select(".novel_info p:nth-child(1) a").text();

        return Response.success({
            name: doc.select(".novel_title").text().trim(),
            cover: doc.select(".lazyload_book_cover").attr("data-src"),
            author: author,
            description: doc.select(".jianjie p").text().trim(),
            // Phần detail lấy toàn bộ bảng thông tin novel_info
            detail: doc.select(".novel_info").html(),
            genres: genres,
            suggests: [
                {
                    title: "Đề cử",
                    input: doc.select(".ui-ranking .ranking-list").html(),
                    script: "suggest.js"
                }
            ],
            host: BASE_URL
        });
    }
    return null;
}