load('transport.js');
function execute(url,page){
 var d=thDoc(url);if(!d)return Response.error('DBG DOC_NULL');
 var title='',body='',all=0,truyen=0;
 try{title=String(d.title()||'');}catch(e){}
 try{body=String(d.select('body').text()||'');}catch(e2){}
 try{all=d.select('a').size();}catch(e3){}
 try{truyen=d.select('a[href*=\"/truyen/\"]').size();}catch(e4){}
 body=body.replace(/\s+/g,' ').replace(/^\s+|\s+$/g,'');
 if(body.length>180)body=body.substring(0,180);
 var name='DBG title='+title+' all='+all+' truyen='+truyen+' body='+body;
 if(name.length>300)name=name.substring(0,300);
 return Response.success([{name:name,link:'https://truyenhub.net/',cover:'',host:'https://truyenhub.net'}],null);
}
