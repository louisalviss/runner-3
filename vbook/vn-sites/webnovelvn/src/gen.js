var BASE_URL='https://webnovel.vn';
function ent(s){return String(s||'').replace(/&amp;/gi,'&').replace(/&quot;/gi,'"').replace(/&#0*39;|&apos;/gi,"'").replace(/&nbsp;/gi,' ').replace(/&#(\d+);/g,function(_,n){return String.fromCharCode(parseInt(n,10)||32);}).replace(/&#x([0-9a-f]+);/gi,function(_,n){return String.fromCharCode(parseInt(n,16)||32);});}
function clean(s){return ent(String(s||'').replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ')).replace(/\s+/g,' ').replace(/^\s+|\s+$/g,'');}
function av(s,n){var r=new RegExp(n+'\\s*=\\s*["\\\']([^"\\\']*)["\\\']','i'),m=r.exec(s||'');return m?ent(m[1]):'';}
function abs(h){h=ent(h);if(/^https?:\/\//i.test(h))return h;return BASE_URL+(h.charAt(0)=='/'?h:'/'+h);}
function isBook(h){
  if(h.indexOf(BASE_URL)!==0)return false;
  var t=h.substring(BASE_URL.length);if(t.charAt(0)=='/')t=t.substring(1);if(t.charAt(t.length-1)=='/')t=t.substring(0,t.length-1);
  if(!t||t.indexOf('/')>=0)return false;
  var bad={all:1,history:1,blog:1,'sach-hay':1,'truyen-moi-dang':1,'truyen-duoc-yeu-thich-nhat':1,'truyen-duoc-xem-nhieu-nhat':1,'truyen-full':1};
  return !bad[t];
}
function execute(url,page){
  page=page||'1';if(String(page)!=='1')return Response.success([],null);
  var r=fetch(url);if(!r.ok)return Response.error('HTTP '+r.status);
  var h=String(r.text()||''),out=[],seen={},re=/<a\b([^>]*)href=["']([^"']+)["']([^>]*)>([\s\S]*?)<\/a>/gi,m;
  while((m=re.exec(h))!==null){
    var u=abs(m[2]);if(!isBook(u)||seen[u])continue;
    var attrs=(m[1]||'')+' '+(m[3]||''),cls=' '+av(attrs,'class')+' ',inside=m[4]||'',im=/<img\b([^>]*)>/i.exec(inside),ia=im?im[1]:'';
    var isUpdate=cls.indexOf(' recently-updated__name ')>=0;
    if(!im&&!isUpdate)continue;
    var name=av(attrs,'title')||av(ia,'alt')||clean(inside);if(!name)continue;
    seen[u]=1;out.push({name:name,link:u,cover:av(ia,'src')||av(ia,'data-src'),host:BASE_URL});
  }
  return out.length?Response.success(out,null):Response.error('NO_ITEM');
}
