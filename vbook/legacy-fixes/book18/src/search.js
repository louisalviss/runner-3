load('config.js');
function execute(key, page) {
    key=String(key||'');
    var p=parseInt(page||'1',10); if(!p||p<1)p=1;
    var response=fetch(BASE_URL+'/?q='+encodeURIComponent(key)+(p>1?'&page='+p:''));
    if(!response.ok) return Response.error('SEARCH_HTTP_'+response.status);
    var doc=response.html(), books=[];
    doc.select('ul.list-group li a[href^="/chapters/"]').forEach(function(a){
        var link=(a.attr('href')||'')+'', name=(a.text()||'').trim(); if(!link||!name)return;
        if(link.indexOf('http')!==0) link=BASE_URL+(link.charAt(0)==='/'?'':'/')+link;
        books.push({name:name,link:link,description:'',host:BASE_URL});
    });
    return Response.success(books, books.length ? String(p+1) : '');
}
