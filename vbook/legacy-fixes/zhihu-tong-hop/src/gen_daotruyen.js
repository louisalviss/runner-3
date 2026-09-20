function execute(path, page) {
    var pageNo = page ? parseInt(page, 10) : 0;
    var url = "https://daotruyen.me" + path + (path.indexOf("?") < 0 ? "?" : "&") + "pageNo=" + pageNo + "&pageSize=8";
    var response = fetch(url, { headers: {
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
        "accept-language": "vi,en;q=0.9",
        "referer": "https://daotruyen.me/",
        "origin": "https://daotruyen.me"
    } });
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var items = json.content || [];
    var data = [];
    for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var cover = item.imageSrc || "";
        if (cover && cover.indexOf("http") !== 0) cover = "https://daotruyen.me" + cover;
        data.push({ name: item.story.name, link: "https://daotruyen.me/api/public/v2/" + item.slug, cover: cover, description: latestChapterDescription(item.timeElapsed), host: "https://daotruyen.me" });
    }
    return Response.success(data, json.last === false ? String(pageNo + 1) : "");
}
load("description.js");
