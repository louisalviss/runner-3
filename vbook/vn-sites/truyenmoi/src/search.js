var BASE_URL='https://truyenmoiss.org';
var UA='Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36';
function getDoc(url){
  try{var r=fetch(url,{headers:{'User-Agent':UA,'Accept':'text/html,application/xhtml+xml','Referer':BASE_URL+'/'}});if(r&&r.ok)return r.html();}catch(e){}
  var b=null;
  try{
    b=Engine.newBrowser();
    try{if(typeof UserAgent!=='undefined'&&UserAgent.chrome)b.setUserAgent(UserAgent.chrome());else b.setUserAgent(UA);}catch(e1){}
    var d=b.launch(url,15000);
    try{if(!d||!d.select||d.select('body').text().indexOf('Just a moment')>=0){sleep(5000);d=b.html();}}catch(e2){}
    return d;
  }catch(e3){return null;}finally{try{if(b)b.close();}catch(e4){}}
}
function abs(h){if(!h)return '';if(String(h).indexOf('http')===0)return String(h);return BASE_URL+(String(h).charAt(0)=='/'?String(h):'/'+String(h));}

function parseList(doc){var out=[],seen={};if(!doc)return out;var es=doc.select('h3.truyen-title a');for(var i=0;i<es.size();i++){var e=es.get(i),h=abs(e.attr('href')),n=e.text();if(!h||!n||seen[h])continue;seen[h]=1;out.push({name:n,link:h,cover:'',host:BASE_URL});}return out;}
function execute(query,page){page=page||'1';if(String(page)!=='1')return Response.success([],null);var url=BASE_URL+'/tim-kiem?tukhoa='+encodeURIComponent(query||'');var d=getDoc(url);if(!d)return Response.error('LOAD_FAIL');var a=parseList(d);return a.length?Response.success(a,null):Response.error('NO_ITEM');}
