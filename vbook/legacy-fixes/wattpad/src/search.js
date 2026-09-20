function execute(key, page) {
    if (!page) page = '0';
    key = String(key || '');
    try { if (key.normalize) key = key.normalize('NFC'); } catch (e) {}
    var data = Http.get("https://www.wattpad.com/v4/search/stories").params({
        query: key,
        fields: "stories(id,title,url,cover,user(name))",
        offset: page,
        limit: "10"
    }).string();
    if (!data) return Response.error("WATTPAD_SEARCH_EMPTY");
    data = JSON.parse(data);
    var next = '';
    if (data.nextUrl) {
        var m = String(data.nextUrl).match(/offset=(\d+)/);
        if (m) next = m[1];
    }
    var novelList = [];
    var stories = data.stories || [];
    for (var i = 0; i < stories.length; i++) {
        var v = stories[i] || {};
        if (!v.url || !v.title) continue;
        novelList.push({
            name: v.title,
            link: v.url,
            cover: v.cover || '',
            description: v.user && v.user.name ? v.user.name : ''
        });
    }
    return Response.success(novelList, next);
}
