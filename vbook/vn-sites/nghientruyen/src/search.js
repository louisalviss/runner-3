load('config.js');load('gen.js');
function execute(query,page){page=page||'1';if(String(page)!=='1')return Response.success([],null);var r=fetch(BASE_URL+'/tim-kiem',{queries:{q:query||''}});if(!r.ok)return Response.error('HTTP '+r.status);return Response.success(parse(r.html()),null);}
