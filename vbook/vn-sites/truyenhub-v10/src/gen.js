load('transport.js');
function execute(url,page){
 var d=thDoc(url);if(!d)return Response.error('DBG DOC_NULL');
 var title='',body='',a=0,t=0;
 try{title=d.title();}catch(e){}
 try{body=String(d.select('body').text()||'');}catch(e2){}
 try{a=d.select('a').size();}catch(e3){}
 try{t=d.select('a[href*=\"/truyen/\"]').size();}catch(e4){}
 body=body.replace(/\s+/g,' ');if(body.length>220)body=body.substring(0,220);
 return Response.error('DBG title='+title+' all='+a+' truyen='+t+' body='+body);
}
