function execute(key, page) {
    key = String(key || '');
    var response = fetch('https://www.dingdian666.com/s.php', {
        method: 'POST',
        headers: {'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.dingdian666.com/','User-Agent':'Mozilla/5.0'},
        body: 's=' + encodeURIComponent(key)
    });
    if (!response.ok) return Response.error('SEARCH_HTTP_' + response.status);
    var doc=response.html(), data=[];
    doc.select('.slist ul li, .search ul li, ul li').forEach(function(item){
        var a=item.select('span.name a[href*="/xiaoshuo/"]').first();
        if(!a) return;
        var link=a.attr('href')||'', name=(a.text()||'').trim(); if(!link||!name) return;
        if(link.indexOf('http')!==0) link='https://www.dingdian666.com'+(link.charAt(0)==='/'?'':'/')+link;
        data.push({name:name,link:link,description:(item.select('span.zuo').text()||'').trim(),host:'https://www.dingdian666.com'});
    });
    return Response.success(data);
}
