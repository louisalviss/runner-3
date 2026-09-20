function execute(key, page) {
    if (!page) page = '1';
    key = String(key || '');
    try { if (key.normalize) key = key.normalize('NFC'); } catch (e) {}
    var response = fetch("http://api.mottruyen.com/tim-kiem/?page_number=" + page + "&k=" + encodeURIComponent(key) + "&os=android");
    if (!response.ok) return Response.error("SEARCH_HTTP_" + response.status);
    var json = response.json() || {};
    var rows = json.data || [];
    var novels = [];
    if (typeof rows.length !== 'number') rows = [];
    for (var i = 0; i < rows.length; i++) {
        var item = rows[i] || {};
        if (!item.ID || !item.NAME) continue;
        novels.push({
            name: item.NAME,
            link: "http://api.mottruyen.com/story/?story_id=" + item.ID,
            cover: item.THUMB || '',
            description: (item.AUTHOR || '') + " - " + (item.PROCESS || '') + "(" + (item.VIEWED || '') + ")"
        });
    }
    return Response.success(novels, novels.length ? String(parseInt(page,10)+1) : '');
}
