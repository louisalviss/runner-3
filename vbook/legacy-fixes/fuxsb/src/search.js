function execute(key,page){
 if(page&&String(page)!=='1')return Response.success([],null);
 var response=fetch('http://www.fuxsb.com/xiandai/');
 if(!response||!response.ok)return Response.error('CAT_HTTP_'+(response?response.status:'0'));
 var doc=response.html(),data=[];
 doc.select('.list_article ul li').forEach(function(e){
  var h2=e.select('h2').first(),a=e.select('h2 a').first(); if(!h2||!a)return;
  var txt=h2.text()||'',name=txt.split('作者：')[0].trim(),desc=(txt.split('作者：')[1]||'').trim();
  var link=a.attr('href')||''; if(!name||!link)return;
  data.push({name:name,cover:'https://i.imgur.com/5BdXa90.png',link:link,description:desc,host:'http://www.fuxsb.com'});
 });
 return Response.success(data,null);
}
