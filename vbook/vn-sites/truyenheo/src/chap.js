load('config.js');

function execute(url) {
    // Chuẩn hóa URL
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    if (url.slice(-1) !== "/") url = url + "/";

    let response = fetch(url);
    if (response.ok) {
        let doc = response.html();

        // Xóa các thành phần rác, quảng cáo
        doc.select('em').remove();
        doc.select('center').remove();
        doc.select('a[target="_blank"]').remove();
        doc.select('#giuabaiviet').remove(); // Xóa khung quảng cáo giữa bài trong DOM mới
        doc.select('.ad-slot').remove();

        // Lấy nội dung từ class mới: .single-content
        let htm = doc.select('.single-content').html();

        if (htm) {
            // Xử lý xuống dòng để hiển thị đẹp hơn trên app
            // Chuyển <br> hoặc ký tự xuống dòng \n thành 2 thẻ <br> để tạo khoảng cách đoạn
            htm = htm.replace(/<br\s*\/?>|\n/gi, "<br><br>");
            
            return Response.success(htm);
        }
    }
    return null;
}