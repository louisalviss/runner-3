load('config.js');

function execute(url) {
    if (url.slice(-1) !== "/") url = url + "/";
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    console.log("test");
    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();
        let genres = [];
        
        // 1. Lấy và làm sạch tên truyện
        let rawName = doc.select('h1.single-title').text().trim();
        // Regex này sẽ xóa bỏ các phần nằm trong ngoặc đơn chứa: update, full, trọn bộ, hoàn thành...
        let cleanName = rawName.replace(/\s*\((update|full|trọn bộ|hoàn thành).*?\)/i, '').trim();

        // 2. Xử lý Tác giả
        let authorTag = doc.select('.single-meta span[itemprop="author"] a').first();
        let authorName = "Không rõ";

        if (authorTag) {
            let rawAuthor = authorTag.text().replace(/Tác giả[:\s]*/i, '').trim();
            if (rawAuthor.length > 0) {
                authorName = rawAuthor;
                genres.push({
                    title: "Tác giả: " + authorName,
                    input: authorTag.attr("href").replace(BASE_URL, ""),
                    script: "gen.js"
                });
            }
        }

        // 3. Lấy các link danh mục trong single-meta (ví dụ: Truyện sex dài tập)
        doc.select('.single-meta span:not([itemprop="author"]) a').forEach(e => {
            let metaTitle = e.text().trim();
            if (metaTitle) {
                genres.push({
                    title: metaTitle,
                    input: e.attr("href").replace(BASE_URL, ""),
                    script: "gen.js"
                });
            }
        });

        // 4. Lấy các tags ở phần footer (single-tags)
        doc.select('.single-tags a.tag-link').forEach(e => {
            let tagTitle = e.text().trim();
            if (tagTitle) {
                genres.push({
                    title: tagTitle,
                    input: e.attr("href").replace(BASE_URL, ""),
                    script: "gen.js"
                });
            }
        });

        return Response.success({
            name: cleanName,
            cover: "https://i.postimg.cc/T2WtdmBM/5BdXa90.webp",
            author: authorName,
            description: 'Nghiêm cấm trẻ em dưới 18 tuổi',
            detail: "Ngày đăng: " + doc.select('time[itemprop="datePublished"]').text().trim(),
            genres: genres,
            host: BASE_URL
        });
    }
    return null;
}