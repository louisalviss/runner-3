load('config.js');

function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL)
    if (url.slice(-1) !== "/") url = url + "/";
    console.log("65454");
    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();
        let data = [];

        // Giữ đúng logic cũ: Nạp mặc định Phần 1 là URL gốc
        data.push({
            name: "Phần 1",
            url: url,
            host: BASE_URL
        })

        // Thay .bai-viet-box bằng .chapter-links để quét các link từ Phần 2 trở đi
        let elems = doc.select('.chapter-links a.post-page-numbers');
        elems.forEach(function(e) {
            data.push({
                name: e.text().trim(),
                url: e.attr('href'),
                host: BASE_URL
            })
        });

        return Response.success(data);
    }
    return null;
}