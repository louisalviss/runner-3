load('gbk.js');
var HOST='http://www.qbtr.cc';
function execute(key,page){
 if(page&&String(page)!=='1')return Response.success([],null);
 key=gbkTrim(String(key||''),30);
 var body='keyboard='+gbkFormEncode(key)+'&show='+encodeURIComponent('title')+'&classid=0';
 var r=fetch('http://www.qbtr.cc/e/search/index.php',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Referer':HOST+'/','User-Agent':'Mozilla/5.0'},body:body});
 if(!r||!r.ok)return Response.error('SEARCH_HTTP_'+(r?r.status:'0'));
 var d=r.html('gbk'),out=[],seen={};
 d.select('.books .bk').forEach(function(e){var a=e.select('h3 a').first();if(!a)return;var link=a.attr('href')||'',name=(a.text()||'').trim();if(!link||!name)return;if(link.indexOf('http')!==0)link=HOST+(link.charAt(0)==='/'?'':'/')+link;if(seen[link])return;seen[link]=1;var img=e.select('img').first();var cover=img?(img.attr('src')||''):'';if(cover&&cover.indexOf('http')!==0)cover=HOST+(cover.charAt(0)==='/'?'':'/')+cover;out.push({name:name,link:link,cover:cover,description:(e.select('.descript, p.intro, p').first().text()||'').trim(),host:HOST});});
 return Response.success(out,null);
}
