load('config.js');
function parse(doc){var out=[],seen={};var es=doc.select('h3.truyen-title a');for(var i=0;i<es.size();i++){var e=es.get(i),h=e.attr('href'),n=e.text();if(!h||!n||seen[h])continue;seen[h]=1;var p=e.parent();out.push({name:n,link:h,cover:'',host:BASE_URL});}return out;}
function execute(url,page){page=page||'1';if(String(page)!=='1')return Response.success([],null);var r=fetch(url);if(!r.ok)return Response.error('HTTP '+r.status);return Response.success(parse(r.html()),null);}
