load('config.js');
function abs(h){if(!h)return '';h=String(h);if(h.indexOf('http://')===0||h.indexOf('https://')===0)return h;return BASE_URL+(h.charAt(0)=='/'?h:'/'+h);}
function execute(url,page){
    var p=(page===null||page===undefined||page===''||String(page)==='0')?'1':String(page);
    if(p!=='1')return Response.success([],null);
    var r=fetch(url);if(!r.ok)return Response.error('HTTP '+r.status);
    var d=r.html(),es=d.select("a[href*='/truyen/']"),out=[],seen={};
    for(var i=0;i<es.size();i++){
        var e=es.get(i),h=abs(e.attr('href')||'');
        if(h.indexOf(BASE_URL+'/truyen/')!==0||h.indexOf('/chuong-')>=0||seen[h])continue;
        var im=e.select('img').first();
        var n=String(e.attr('title')||e.text()||(im?im.attr('alt'):'')||'').trim();
        if(!n&&im)n=String(im.attr('alt')||'').trim();
        if(!n)continue;
        var c=im?String(im.attr('data-src')||im.attr('data-lazy-src')||im.attr('src')||''):'';
        c=abs(c);
        seen[h]=1;out.push({name:n,link:h,cover:c,host:BASE_URL});
    }
    return out.length?Response.success(out,null):Response.error('NO_ITEM');
}
