load('config.js');
function nfc(s){s=String(s||'');try{if(s.normalize)s=s.normalize('NFC');}catch(e){}return s;}
function fold(s){s=nfc(s).toLowerCase();try{if(s.normalize)s=s.normalize('NFD');}catch(e){}s=s.replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');return s.replace(/[^a-z0-9]+/g,' ').replace(/^\s+|\s+$/g,'').replace(/\s+/g,' ');}
function abs(h){h=String(h||'');if(!h)return '';if(h.indexOf('http://')===0||h.indexOf('https://')===0)return h;return BASE_URL.replace(/\/$/,'')+'/'+h.replace(/^\/+/, '');}
function parse(doc,q,out,seen){
  doc.select('.post-list .post-item').forEach(function(e){
    var a=e.select('.post-title a').first(); if(a===null)return;
    var name=String(a.text()||'').replace(/^\s+|\s+$/g,''); var link=abs(a.attr('href'));
    var f=fold(name); if(!name||!link||seen[link]||!(f===q||f.indexOf(q)>=0||q.indexOf(f)>=0))return;
    seen[link]=1;
    var author=String(e.select('.post-author').text()||'').replace(/Tác giả[:\s]*/i,'').replace(/^\s+|\s+$/g,'');
    out.push({name:name,link:link,cover:'https://i.postimg.cc/T2WtdmBM/5BdXa90.webp',description:author,host:BASE_URL});
  });
}
function execute(key,page){
  if(page&&String(page)!=='0'&&String(page)!=='1')return Response.success([],null);
  var q=fold(key); if(!q)return Response.success([],null);
  var out=[],seen={};
  for(var p=1;p<=5;p++){
    var u=BASE_URL.replace(/\/$/,'')+'/' + (p===1?'':'page/'+p+'/');
    var r=fetch(u); if(!r||!r.ok)continue; parse(r.html(),q,out,seen); if(out.length)break;
  }
  return Response.success(out,null);
}
