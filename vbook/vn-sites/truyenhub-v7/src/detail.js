load('transport.js');
var BASE_URL='https://truyenhub.net';
function thAbs(h){h=String(h||'');if(!h)return '';if(h.indexOf('http://')===0||h.indexOf('https://')===0)return h;if(h.charAt(0)!='/')h='/'+h;return BASE_URL+h;}
function thEnt(s){s=String(s||'');s=s.replace(/&nbsp;|&#160;/gi,' ').replace(/&amp;/gi,'&').replace(/&quot;/gi,'"').replace(/&#39;|&apos;/gi,"'").replace(/&lt;/gi,'<').replace(/&gt;/gi,'>');return s.replace(/&#(x?[0-9a-f]+);/gi,function(a,n){var v=n.charAt(0).toLowerCase()==='x'?parseInt(n.substring(1),16):parseInt(n,10);return isNaN(v)?a:String.fromCharCode(v);});}
function thAttr(tag,name){var r=new RegExp('\\b'+name+'\\s*=\\s*(["\\\'])'+'([^"\\\']*)'+'\\1','i'),m=r.exec(String(tag||''));return m?thEnt(m[2]):'';}
function thText(s){s=String(s||'').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ').replace(/<br\s*\/?\s*>/gi,' ').replace(/<[^>]+>/g,' ');return thEnt(s).replace(/\s+/g,' ').replace(/^\s+|\s+$/g,'');}

function thMeta(h,k,v){var re=/<meta\b[^>]*>/gi,m;while((m=re.exec(h))!==null){var tag=m[0];if(String(thAttr(tag,k)||'').toLowerCase()===String(v||'').toLowerCase())return thAttr(tag,'content');}return '';}
function execute(url){var h=thBrowserGet(url);if(!h)return Response.error('browser transport'),m=/<h1\b[^>]*>([\s\S]*?)<\/h1>/i.exec(h),name=m?thText(m[1]):'',cover=thMeta(h,'property','og:image'),desc=thMeta(h,'name','description'),author='',ar=/<([a-z0-9]+)\b[^>]*class\s*=\s*(["'])[^"']*author-link[^"']*\2[^>]*>([\s\S]*?)<\/\1>/i.exec(h);if(ar)author=thText(ar[3]);if(!name)name=url;return Response.success({name:name,cover:thAbs(cover),author:author,description:desc,host:BASE_URL,ongoing:true});}
