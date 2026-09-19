load('config.js');
function abs(h){if(!h)return ''; if(h.indexOf('http')===0)return h; if(h.charAt(0)!='/')h='/'+h; return BASE_URL+h;}
function execute(url,page){
  if(page && String(page)!=='1') return Response.success([], null);
  let r=fetch(url,{headers:HTTP_HEADERS}); if(!r.ok)return Response.error('HTTP '+r.status); let d=r.html(); let out=[],seen={};
  d.select("a[href*='/truyen/']").forEach(e=>{
    let h=e.attr('href')||''; if(!/^https?:\/\/hibook\.net\/truyen\/[^/?#]+\/?$/.test(h) && !/^\/truyen\/[^/?#]+\/?$/.test(h))return;
    h=abs(h); if(/\/truyen\/(moi-cap-nhat|yeu-thich|doc-quyen|hoan-thanh|luu-nhieu)\/?$/.test(h))return; if(/\/truyen\/(moi-cap-nhat|yeu-thich|doc-quyen|hoan-thanh|luu-nhieu)\/?$/.test(h))return; if(seen[h])return; seen[h]=1;
    let img=e.select('img').first(); let name=(e.attr('title')||e.text()||(img?img.attr('alt'):'')||'').trim();
    if(!name && img) name=(img.attr('alt')||'').trim(); if(!name)return;
    let cover=img?(img.attr('data-src')||img.attr('src')||''):'';
    out.push({name:name,link:h,cover:cover,host:BASE_URL});
  });
  return Response.success(out,null);
}
