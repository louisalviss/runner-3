load('config.js');
function execute(key, page) {
    key = String(key || '');
    try { if (key.normalize) key = key.normalize('NFC'); } catch (e) {}
    if (!page) page = 1;
    var response = fetch(BASE_URL + '/search.html?q=' + encodeURIComponent(key) + '&p=' + page, {
        headers: {'user-agent': UserAgent.chrome()}
    });
    if (!response || !response.ok) return Response.error('SEARCH_HTTP_' + (response ? response.status : '0'));
    var doc = response.html();
    var data = [];
    var elems = doc.select('.list-group .list-group-item');
    for (var i = 0; i < elems.size(); i++) {
        var e = elems.get(i);
        var a = e.select('h5 a').first();
        if (!a) continue;
        var link = (a.attr('href') || '') + '';
        var name = (a.text() || '') + '';
        name = name.replace(/^\s*\d+\.\s*/, '').trim();
        if (!link || !name) continue;
        if (link.indexOf('//') === 0) link = 'https:' + link;
        else if (link.indexOf('http') !== 0) link = 'https://www.alicesw.com' + (link.charAt(0) === '/' ? '' : '/') + link;
        data.push({
            name: name,
            link: link,
            cover: 'https://i.postimg.cc/T2WtdmBM/5BdXa90.webp',
            description: e.select('.text-muted').text(),
            host: 'https://www.alicesw.com'
        });
    }
    return Response.success(data, data.length ? String(parseInt(page, 10) + 1) : '');
}
