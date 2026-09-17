load('config.js');
function execute(url) {
    url = normalizeUrl(url);
    let slug = getSlug(url);
    if (!slug) return Response.error("Không xác định được slug truyện");
    let response = fetch(BASE_URL + "/api/reading/" + encodeURIComponent(slug));
    if (!response.ok) return Response.error("HTTP " + response.status);
    let book = response.json();
    let tags = [];
    let categories = book && book.categories ? book.categories : [];
    for (let i = 0; i < categories.length; i++) {
        tags.push({ title: String(categories[i].name || ""), input: String(categories[i].slug || ""), script: "cate.js" });
    }
    let author = book && book.author && book.author.name ? String(book.author.name) : "";
    let status = book && book.status === "D" ? "Hoàn thành" : "Đang ra";
    let updated = book && book.updatedAt ? String(book.updatedAt) : "";
    return Response.success({
        name: book && book.name ? String(book.name) : slug,
        author: author,
        cover: coverUrl(book ? book.cover : null),
        description: book && book.intro ? String(book.intro) : "",
        detail: "Tác giả: " + author + "<br>Trạng thái: " + status + (updated ? "<br>Cập nhật: " + updated : ""),
        url: BASE_URL + "/" + slug,
        type: "novel",
        format: "novel",
        ongoing: !(book && book.status === "D"),
        tags: tags
    });
}
