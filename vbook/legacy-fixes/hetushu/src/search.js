function execute(key, page) {
    key = String(key || '');
    try { if (key.normalize) key = key.normalize('NFC'); } catch (e) {}
    if (page && String(page) !== '1') return Response.success([], null);
    var host = 'https://www.hetushu.com';
    var doc = Http.get(host + '/search/').params({keyword:key}).html();
    var data = [];
    doc.select('#body dd').forEach(function(item) {
        var a = item.select('h4 a').first();
        if (!a) return;
        var name = (a.text() || '').trim();
        var link = a.attr('href') || '';
        if (!name || !link) return;
        if (link.indexOf('http') !== 0) link = host + (link.charAt(0) === '/' ? '' : '/') + link;
        var cover = item.select('img').first().attr('src') || '';
        if (cover && cover.indexOf('http') !== 0) cover = host + (cover.charAt(0) === '/' ? '' : '/') + cover;
        data.push({name:name, link:link, cover:cover, description:(item.select('.intro').text() || '').trim(), host:host});
    });
    return Response.success(data, null);
}
