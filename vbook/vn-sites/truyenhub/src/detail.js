load('config.js');
function execute(url){let r=fetch(url); if(!r.ok)return Response.error('HTTP '+r.status); let d=r.html();
 let name=d.select('h1').first().text(); if(!name)name=d.select('meta[property=og:title]').attr('content');
 let cover=d.select('meta[property=og:image]').attr('content'); let desc=d.select('meta[name=description]').attr('content');
 let author=d.select(".author-link").first().text();
 return Response.success({name:name||url,cover:cover||'',author:author||'',description:desc||'',host:BASE_URL,ongoing:true});}
