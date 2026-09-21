var TH_UA='Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36';
function thDoc(url){
 var b=null,d=null;
 try{
  b=Engine.newBrowser();
  try{if(typeof UserAgent!=='undefined'&&UserAgent.chrome)b.setUserAgent(UserAgent.chrome());else b.setUserAgent(TH_UA);}catch(e0){}
  try{d=b.launch(url,20000);}catch(e1){try{b.launchAsync(url);sleep(7000);d=b.html(5000);}catch(e2){d=null;}}
  if(!d||!d.select){try{sleep(4000);d=b.html(5000);}catch(e3){d=null;}}
  if(d&&d.select){
   try{var t=d.select('body').text();if(!t||t.indexOf('Just a moment')>=0||t.indexOf('Checking your browser')>=0){sleep(7000);d=b.html(5000);}}catch(e4){}
  }
  return d;
 }catch(e){return null;}finally{try{if(b)b.close();}catch(e5){}}
}
