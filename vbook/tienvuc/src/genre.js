load('config.js');
function execute() {
    let response = fetch(BASE_URL + "/api/categories/all");
    if (!response.ok) return Response.error("HTTP " + response.status);
    let json = response.json();
    let data = [];
    for (let i = 0; i < json.length; i++) {
        data.push({ title: String(json[i].name || ""), input: String(json[i].slug || ""), script: "cate.js" });
    }
    return Response.success(data);
}
