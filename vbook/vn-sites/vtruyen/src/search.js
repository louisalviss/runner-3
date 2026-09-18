load('config.js'); load('gen.js');
function execute(key,page){return executeSearch(key,page);}
function executeSearch(key,page){
  let u="https://vtruyen.vn/kham-pha/tim-kiem?keyword="+encodeURIComponent(key||'');
  if(page && String(page)!=='1')return Response.success([],null);
  let r=fetch(u); if(!r.ok)return Response.error('HTTP '+r.status); let d=r.html(); let out=[],seen={};
  d.select("a[href*='/tac-pham/']").forEach(e=>{let h=e.attr('href')||''; if(h.indexOf("/tac-pham/")<0||h.indexOf("/truyen-chu/")>=0)return; if(h.indexOf('http')!==0)h=BASE_URL+(h.charAt(0)=='/'?h:'/'+h); if(seen[h])return; seen[h]=1; let img=e.select('img').first(); let name=(e.attr('title')||e.text()||(img?img.attr('alt'):'')||'').trim(); if(!name&&img)name=(img.attr('alt')||'').trim(); if(name)out.push({name:name,link:h,cover:img?(img.attr('data-src')||img.attr('src')||''):'',host:BASE_URL});});
  return Response.success(out,null);
}
