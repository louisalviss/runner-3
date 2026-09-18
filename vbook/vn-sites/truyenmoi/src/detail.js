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

function execute(url){var d=getDoc(url);if(!d)return Response.error('LOAD_FAIL');var name=d.select('h1.story-title').first().text();if(!name)name=d.select('h1').first().text();var desc=d.select('.desc-text').first().html();if(!desc)desc=d.select('.story-ablout').first().html();var img=d.select('img').first();var cover=img?abs(img.attr('src')||img.attr('data-src')):'';return Response.success({name:name||url,author:'',cover:cover,description:desc||'',detail:'',url:url,type:'novel',format:'novel',ongoing:true});}
