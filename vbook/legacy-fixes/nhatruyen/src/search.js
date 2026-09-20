load('config.js');
function execute(key, page) {
    key=String(key||'');
    try{if(key.normalize)key=key.normalize('NFC');}catch(e){}
    var p=parseInt(page||'1',10); if(!p||p<1)p=1;
    var response=fetch(BASE_URL+'/?s='+encodeURIComponent(key)+(p>1?'&paged='+p:''));
    if(!response.ok) return Response.error('SEARCH_HTTP_'+response.status);
    var doc=response.html(), books=[];
    doc.select('article.entry-card').forEach(function(el){
        var a=el.select('h2.entry-title a[href*="/truyen/"]').first(); if(!a)return;
        var link=(a.attr('href')||'')+'', name=(a.text()||'').trim(); if(!link||!name)return;
        var img=el.select('img').first(), cover=''; if(img)cover=img.attr('data-src')||img.attr('src')||'';
        books.push({name:name,link:link,cover:cover,description:(el.select('.entry-excerpt').text()||'').trim(),host:BASE_URL});
    });
    var hasNext=doc.select('a.next.page-numbers').size()>0;
    return Response.success(books,hasNext?String(p+1):'');
}
