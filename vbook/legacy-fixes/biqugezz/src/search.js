load('config.js');
load('gbk.js');
var HOST='https://www.biqugezz.com';
function execute(key,page){
 if(page&&String(page)!=='1')return Response.success([],null);
 key=gbkTrim(String(key||''),48);
 var body='searchkey='+gbkFormEncode(key)+'&action=login';
 var r=fetch('https://www.biqugezz.com/modules/article/search.php',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Referer':HOST+'/modules/article/search.php','User-Agent':'Mozilla/5.0'},body:body});
 if(!r||!r.ok)return Response.error('SEARCH_HTTP_'+(r?r.status:'0'));
 var d=r.html('gbk'),out=[];
 var title=(d.select('meta[property="og:title"]').attr('content')||'').trim();
 var link=(d.select('link[rel="canonical"]').attr('href')||'').trim();
 if(title&&link)out.push({name:title,link:link,description:(d.select('meta[property="og:description"]').attr('content')||'').trim(),host:HOST});
 if(!out.length) d.select('#fengtui .bookbox, .bookbox').forEach(function(e){var a=e.select('h4 a').first();if(!a)return;var n=(a.text()||'').trim(),u=a.attr('href')||'';if(!n||!u)return;if(u.indexOf('http')!==0)u=HOST+(u.charAt(0)==='/'?'':'/')+u;out.push({name:n,link:u,description:(e.select('.author').text()||'').trim(),host:HOST});});
 return Response.success(out,null);
}
