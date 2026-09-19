var BASE_URL='https://webnovel.vn';
function isBook(h){
  if(h.indexOf(BASE_URL)!==0)return false;
  var t=h.substring(BASE_URL.length);
  if(t.charAt(0)=='/')t=t.substring(1);
  if(t.charAt(t.length-1)=='/')t=t.substring(0,t.length-1);
  if(!t||t.indexOf('/')>=0)return false;
  var bad={all:1,history:1,blog:1,'sach-hay':1,'truyen-moi-dang':1,'truyen-duoc-yeu-thich-nhat':1,'truyen-duoc-xem-nhieu-nhat':1,'truyen-full':1};
  return !bad[t];
}
function execute(url,page){
  page=page||'1'; if(String(page)!=='1')return Response.success([],null);
  var r=fetch(url); if(!r.ok)return Response.error('HTTP '+r.status);
  var d=r.html(),es=d.select('a[href]'),out=[],seen={};
  for(var i=0;i<es.size();i++){
    var e=es.get(i),h=e.attr('href')||'';
    if(h.indexOf('http')!==0)h=BASE_URL+(h.charAt(0)=='/'?h:'/'+h);
    if(!isBook(h)||seen[h])continue;
    var im=e.select('img').first();
    var cls=String(e.attr('class')||'');
    var isUpdate=cls.indexOf('recently-updated__name')>=0;
    if(!im&&!isUpdate)continue;
    var n=(e.attr('title')||e.text()||(im?im.attr('alt'):'')||'').trim();
    if(!n)continue;
    seen[h]=1;
    out.push({name:n,link:h,cover:im?(im.attr('src')||''):'',host:BASE_URL});
  }
  return Response.success(out,null);
}
