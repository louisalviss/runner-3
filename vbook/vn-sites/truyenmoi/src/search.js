var BASE_URL='https://truyenmoiss.org';
function parseList(doc){var out=[],seen={};var es=doc.select('h3.truyen-title a');for(var i=0;i<es.size();i++){var e=es.get(i),h=e.attr('href'),n=e.text();if(!h||!n||seen[h])continue;seen[h]=1;out.push({name:n,link:h,cover:'',host:BASE_URL});}return out;}
function execute(query,page){page=page||'1';if(String(page)!=='1')return Response.success([],null);var r=fetch(BASE_URL+'/tim-kiem',{queries:{tukhoa:query||''}});if(!r.ok)return Response.error('HTTP '+r.status);return Response.success(parseList(r.html()),null);}
