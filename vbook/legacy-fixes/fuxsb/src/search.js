load('gbk.js');
var HOST='http://www.fuxsb.com';
function norm(s){return String(s||'').toLowerCase().replace(/\s+/g,'').replace(/[()（）【】\[\]·・:：,，.!！?？\-—_]/g,'');}
function abs(u){u=String(u||'');if(!u)return '';if(/^https?:\/\//i.test(u))return u.replace('https://www.fuxsb.com','http://www.fuxsb.com');return HOST+(u.charAt(0)==='/'?'':'/')+u;}
function itemsFrom(doc){
 var out=[],seen={};
 doc.select('.list_article li, .list_article ul li').forEach(function(item){
  var a=item.select('h2 a').first(); if(!a)return;
  var link=abs(a.attr('href')||''), name=(a.text()||'').trim(); if(!link||!name||seen[link])return;
  seen[link]=1; out.push({name:name,link:link,description:(item.select('.like').text()||item.select('.desc').text()||'').trim(),host:HOST});
 });
 return out;
}
function matchItems(a,key){var q=norm(key),out=[];for(var i=0;i<a.length;i++){var n=norm(a[i].name);if(n&&(n.indexOf(q)>=0||q.indexOf(n)>=0))out.push(a[i]);}return out;}
function fallbackCatalog(key){
 var cats=['/xiandai/','/gudai/','/chuanyue/','/qihuan/','/wangyou/','/tongren/','/baihe/'];
 var q=norm(key),out=[],seen={};
 for(var i=0;i<cats.length;i++){
  var r=fetch(HOST+cats[i],{headers:{'User-Agent':'Mozilla/5.0'}}); if(!r||!r.ok)continue;
  var doc=r.html();
  doc.select('.list_article ul li').forEach(function(e){
   var h2=e.select('h2').first(),a=e.select('h2 a').first(); if(!h2||!a)return;
   var name=(h2.text()||'').split('作者：')[0].trim();
   var link=abs(a.attr('href')||''); if(!name||!link||seen[link])return;
   var n=norm(name); if(!(n.indexOf(q)>=0||q.indexOf(n)>=0))return;
   seen[link]=1; out.push({name:name,link:link,description:(h2.text()||'').split('作者：')[1]||'',host:HOST});
  });
  if(out.length)break;
 }
 return Response.success(out,null);
}
function execute(key,page){
 key=gbkTrim(String(key||''),30);
 if(page&&/^https?:\/\//i.test(String(page))){var rp=fetch(String(page));return Response.success(itemsFrom(rp.html('gbk')),null);}
 if(page&&String(page)!=='1')return Response.success([],null);
 var body='keyboard='+gbkFormEncode(key)+'&show=title%2Cwriter%2Ckeyboard&tempid=1&tbname=article';
 var r=fetch('https://www.fuxsb.com/e/search/index.php',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded','Referer':'https://www.fuxsb.com/','User-Agent':'Mozilla/5.0','Cookie':'cjtxmlastsearchtime=0'},body:body});
 if(r&&r.ok){var a=itemsFrom(r.html('gbk'));if(a.length)return Response.success(a,null);}
 return fallbackCatalog(key);
}
