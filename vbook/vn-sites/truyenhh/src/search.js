load('config.js'); load('gen.js');
function normQuery(s){s=String(s||'');try{if(s.normalize)s=s.normalize('NFC');}catch(e){}return s;}
function execute(key,page){return executeSearch(normQuery(key),page);}
function executeSearch(key,page){
  key=normQuery(key);
  let u="https://truyenhh.com/?s="+encodeURIComponent(key||'');
  if(page && String(page)!=='1')return Response.success([],null);
  let r=fetch(u); if(!r.ok)return Response.error('HTTP '+r.status); let d=r.html(); let out=[],seen={};
  d.select("a[href*='/truyen/']").forEach(e=>{
    let h=e.attr('href')||'';
    if(!/^https?:\/\/truyenhh\.com\/truyen\/[^/?#]+\/?$/.test(h) && !/^\/truyen\/[^/?#]+\/?$/.test(h))return;
    if(h.indexOf('http')!==0)h=BASE_URL+(h.charAt(0)=='/'?h:'/'+h);
    if(seen[h])return;
    let img=e.select('img').first();
    let name=(e.attr('title')||e.text()||(img?img.attr('alt'):'')||'').trim();
    if(!name&&img)name=(img.attr('alt')||'').trim();
    if(!name)return;
    seen[h]=1;
    out.push({name:name,link:h,cover:img?(img.attr('data-src')||img.attr('src')||''):'',host:BASE_URL});
  });
  return Response.success(out,null);
}
