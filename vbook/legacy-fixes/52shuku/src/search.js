load('config.js');
function execute(key, page) {
    key = String(key || '');
    try { if (key.normalize) key = key.normalize('NFC'); } catch (e) {}
    if (page && String(page) !== '1') return Response.success([], null);
    var response = fetch(BASE_URL + '/so/search.php?q=' + encodeURIComponent(key));
    if (!response || !response.ok) return Response.error('SEARCH_HTTP_' + (response ? response.status : '0'));
    var doc = response.html();
    var data = [];
    doc.select('article.excerpt').forEach(function(item) {
        var a = item.select('h2 a').first();
        if (!a) return;
        var link = a.attr('href') || '';
        var name = (a.select('h4').text() || a.text() || '').replace(/^\s*\d+\.\s*/, '').trim();
        if (!link || !name) return;
        if (link.indexOf('http') !== 0) link = BASE_URL + (link.charAt(0) === '/' ? '' : '/') + link;
        data.push({name:name, link:link, description:(item.select('.note').text() || '').trim(), host:BASE_URL});
    });
    return Response.success(data, null);
}
