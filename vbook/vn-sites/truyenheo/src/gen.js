load('config.js');

function execute(url, page) {
    if (!page) {
        page = '';
    } else {
        page = `page/${page}/`;
    }

    let newUrl = BASE_URL + url + page;
    let response = fetch(newUrl);

    if (response.ok) {
        let doc = response.html();
        let data = [];

        doc.select(".post-list .post-item").forEach(e => {
            let titleLink = e.select('.post-title a');
            let name = titleLink.text().trim();
            
            if (name) {
                // 1. Tags: Lấy ngược, giới hạn 3 cái đầu tiên sau khi đảo để tránh tràn dòng
                let tags = [];
                e.select('.post-tags a').forEach(tag => {
                    let t = tag.text().trim();
                    if (t) tags.push(t);
                });
                let tagStr = tags.reverse().slice(0, 3).join(', ');

                // 2. Tác giả: Xóa chữ "Tác giả:" cho đỡ tốn diện tích
                let author = e.select('.post-author').text().replace(/Tác giả[:\s]*/i, '').trim();

                // 3. Tóm tắt: Cắt ngắn hẳn (60 ký tự)
                let excerpt = e.select('.post-excerpt').text().trim();
                if (excerpt.length > 60) {
                    excerpt = excerpt.substring(0, 60) + "...";
                }

                // 4. Ghép lại theo cấu trúc: [Tags] | [Tác giả] - [Tóm tắt]
                let descParts = [];
                if (tagStr) descParts.push(tagStr);
                if (author) descParts.push(author);
                
                let mainDesc = descParts.join(' | ');
                let finalDescription = mainDesc + (excerpt ? " - " + excerpt : "");

                data.push({
                    name: name,
                    link: titleLink.attr('href'),
                    cover: "https://i.postimg.cc/T2WtdmBM/5BdXa90.webp",
                    description: finalDescription,
                    host: BASE_URL
                });
            }
        });

        let next = doc.select('span.page-numbers.current + a.page-numbers').text().trim();
        if (next) return Response.success(data, next);

        return Response.success(data);
    }
    return null;
}