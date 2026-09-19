load('config.js');
function abs(h){if(!h)return ''; if(h.indexOf('http')===0)return h; return BASE_URL+(h.charAt(0)=='/'?h:'/'+h);}
function execute(url){let r=fetch(url,{headers:HTTP_HEADERS}); if(!r.ok)return Response.error('HTTP '+r.status); let d=r.html(); let out=[],seen={}; d.select("a[href*='/chuong/']").forEach(e=>{let h=abs(e.attr('href')); if(!h||seen[h])return; seen[h]=1; let n=(e.text()||e.attr('title')||'Chương').trim(); out.push({name:n,url:h,host:BASE_URL,lock:false,pay:false});}); return Response.success(out);}
