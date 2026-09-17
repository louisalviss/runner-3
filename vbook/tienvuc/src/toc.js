load('config.js');
function execute(url) {
    url = normalizeUrl(url);
    let slug = getSlug(url);
    if (!slug) return Response.error("Không xác định được slug truyện");
    let response = fetch(BASE_URL + "/api/reading/" + encodeURIComponent(slug) + "/chapters");
    if (!response.ok) return Response.error("HTTP " + response.status);
    let json = response.json();
    let docs = json && json.docs ? json.docs : [];
    let chapters = [];
    for (let i = 0; i < docs.length; i++) {
        let chap = docs[i];
        let num = String(chap.num);
        let title = "Chương " + num;
        if (chap.name) title += ": " + String(chap.name);
        chapters.push({
            name: title,
            url: BASE_URL + "/" + slug + "/chuong-" + num,
            description: "",
            lock: false,
            pay: Number(chap.coins || 0) > 0 && chap.isBought !== true
        });
    }
    return Response.success(chapters);
}
