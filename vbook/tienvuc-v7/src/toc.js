load('config.js');
function execute(url) {
    let slug = getSlug(url);
    if (!slug) return Response.error("V4 SLUG_INVALID");
    let response = fetch(BASE_URL + "/api/reading/" + encodeURIComponent(slug) + "/chapters");
    if (!response.ok) return Response.error("V4 HTTP " + response.status);
    let json = response.json();
    let docs = json && json.docs ? json.docs : [];
    let chapters = [];
    for (let i = 0; i < docs.length; i++) {
        let c = docs[i], num = String(c.num);
        let title = "Chương " + num + (c.name ? ": " + String(c.name) : "");
        chapters.push({name:title,url:synthChapUrl(slug,num),description:"V4",lock:false,pay:Number(c.coins||0)>0&&c.isBought!==true});
    }
    return Response.success(chapters);
}
