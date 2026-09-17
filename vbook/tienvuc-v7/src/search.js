load('config.js');
function execute(query, page) {
    query = query || "";
    page = page || "1";
    let response = fetch(BASE_URL + "/api/search", {
        method: "GET",
        queries: { search: query, page: page, limit: "20" }
    });
    if (!response.ok) return Response.error("HTTP " + response.status);
    let json = response.json();
    let docs = json && json.docs ? json.docs : [];
    let items = [];
    for (let i = 0; i < docs.length; i++) items.push(bookItem(docs[i]));
    let current = parseInt(page, 10) || 1;
    let total = parseInt(json.totalDocs, 10) || 0;
    let next = current * 20 < total ? String(current + 1) : "";
    return Response.success(items, next);
}
