load('gbk.js');
function execute(key, page) {
    key = gbkTrim(String(key || ''), 30);
    if (page && /^https?:\/\//i.test(String(page))) return parseResult(fetch(String(page)));
    var body = 'keyboard=' + gbkFormEncode(key) + '&show=title%2Cwriter%2Ckeyboard&tempid=1&tbname=article';
    var response = fetch('https://www.fuxsb.com/e/search/index.php', {
        method: 'POST',
        headers: {'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.fuxsb.com/','User-Agent':'Mozilla/5.0'},
        body: body
    });
    return parseResult(response);
}
function parseResult(response) {
    if (!response || !response.ok) return Response.error('SEARCH_HTTP_' + (response ? response.status : '0'));
    var doc = response.html('gbk'), data = [];
    doc.select('.list_article li').forEach(function(item){
        var a=item.select('h2 a').first(); if(!a) return;
        var link=a.attr('href')||'', name=(a.text()||'').trim(); if(!link||!name) return;
        if(link.indexOf('http')!==0) link='https://www.fuxsb.com'+(link.charAt(0)==='/'?'':'/')+link;
        data.push({name:name,link:link,description:(item.select('.like').text()||'').trim(),host:'https://www.fuxsb.com'});
    });
    var next=doc.select('.dede_pages a').last().attr('href')||'';
    if(next && next.indexOf('http')!==0) next='https://www.fuxsb.com'+(next.charAt(0)==='/'?'':'/')+next;
    return Response.success(data,next);
}
