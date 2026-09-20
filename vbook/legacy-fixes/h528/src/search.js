load('config.js');
function execute(key, page) {
    key = String(key || '');
    var p = parseInt(page || '1', 10); if (!p || p < 1) p = 1;
    var url = BASE_URL + '/?s=' + encodeURIComponent(key);
    if (p > 1) url += '&paged=' + p;
    var response = fetch(url);
    if (!response.ok) return Response.error('SEARCH_HTTP_' + response.status);
    var doc=response.html(), books=[];
    doc.select('#content h3 a[rel=bookmark]').forEach(function(a){
        var link=(a.attr('href')||'')+'', name=(a.text()||'').trim();
        if(!link||!name) return;
        books.push({name:name,link:link,description:'',host:BASE_URL});
    });
    return Response.success(books, books.length ? String(p+1) : '');
}
