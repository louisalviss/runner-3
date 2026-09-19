var BASE_URL='https://nghientruyen.net';
function normQuery(s){s=String(s||'');try{if(s.normalize)s=s.normalize('NFC');}catch(e){}return s.replace(/^\s+|\s+$/g,'');}
function fold(s){s=String(s||'').toLowerCase();try{if(s.normalize)s=s.normalize('NFD');}catch(e){}s=s.replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d');return s.replace(/[^a-z0-9]+/g,' ').replace(/^\s+|\s+$/g,'').replace(/\s+/g,' ');}
function slugify(s){return fold(s).replace(/\s+/g,'-');}
function score(title,q){var t=fold(title),f=fold(q);if(!f)return 0;if(t===f)return 100;if(t.indexOf(f)===0)return 90;if(t.indexOf(f)>=0)return 80;var a=f.split(' '),hit=0;for(var i=0;i<a.length;i++)if(a[i]&&t.indexOf(a[i])>=0)hit++;return a.length?Math.round(hit*50/a.length):0;}
function extractTitle(html){var m=/<h1[^>]*>([\s\S]*?)<\/h1>/i.exec(html||'');if(!m)m=/<title[^>]*>([\s\S]*?)<\/title>/i.exec(html||'');if(!m)return '';var s=String(m[1]||'').replace(/<[^>]+>/g,' ').replace(/&[^;]+;/g,' ').replace(/\s+/g,' ').replace(/^\s+|\s+$/g,'');s=s.replace(/\s*-\s*Nghiện Truyện\s*$/i,'');return s;}
function execute(query,page){
  var p=page||'1';if(String(p)!=='1')return Response.success([],null);
  var q=normQuery(query);if(!q)return Response.success([],null);
  var out=[],seen={};
  // Deterministic exact-title fallback: most Nghiện Truyện story URLs are the folded title slug.
  var direct=BASE_URL+'/doc-truyen/'+slugify(q);
  try{var dr=fetch(direct);if(dr&&dr.ok){var dn=extractTitle(dr.text())||q;if(dn&&fold(dn)===fold(q)){out.push({name:dn,link:direct,cover:'',host:BASE_URL,_s:120,_i:-1});seen[direct]=1;}}}catch(e){}
  var r=null;try{r=fetch(BASE_URL+'/api/search-suggest',{queries:{q:q},headers:{'Accept':'application/json'}});}catch(e2){}
  if(r&&r.ok){var data=[];try{data=r.json()||[];}catch(e3){data=[];}for(var i=0;i<data.length;i++){var x=data[i]||{},u=String(x.url||''),n=String(x.title||'');if(!u||!n||u.indexOf(BASE_URL+'/doc-truyen/')!==0||seen[u])continue;seen[u]=1;out.push({name:n,link:u,cover:'',host:BASE_URL,_s:score(n,q),_i:i});}}
  out.sort(function(a,b){return b._s-a._s||a._i-b._i;});for(var j=0;j<out.length;j++){delete out[j]._s;delete out[j]._i;}
  return Response.success(out,null);
}
