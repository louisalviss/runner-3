load('config.js');
function execute(key) {
    key=String(key||'');
    var response=fetch(BASE_URL+'/search?keyword='+encodeURIComponent(key));
    var novelList=[];
    if(response.ok){
        var doc=response.html();
        doc.select('#list-page .col-novel-main .list-novel > .row').forEach(function(e){
            var a=e.select('.novel-title a').first(); if(!a)return;
            var name=(a.text()||'').replace(/<[^>]+>/g,'').trim();
            var link=toUrl(a.attr('href')||''); if(!name||!link)return;
            var cover=e.select('.cover').first().attr('data-src')||e.select('.cover').first().attr('src')||'';
            novelList.push({name:name,link:link,description:e.select('.author').text(),cover:toUrl(cover),host:BASE_URL});
        });
    }
    var folded=fold(key);
    for(var i=0;i<novelList.length;i++){ if(fold(novelList[i].name)===folded) return Response.success(novelList); }
    var slug=slugify(key);
    if(slug){
        var direct=BASE_URL+'/novelnext/'+slug+'/';
        var dr=fetch(direct);
        if(dr.ok){
            var dd=dr.html();
            var title=(dd.select('h1').first().text()||dd.select('meta[property=og:title]').attr('content')||key)+' ';
            title=title.replace(/\s*[|\-–]\s*Novel Next.*$/i,'').trim();
            if(title) novelList.unshift({name:title,link:direct,cover:dd.select('meta[property=og:image]').attr('content')||'',description:'',host:BASE_URL});
        }
    }
    return Response.success(novelList);
}
function fold(s){return String(s||'').toLowerCase().replace(/\s+/g,' ').trim();}
function slugify(s){return String(s||'').toLowerCase().replace(/[\*'’]/g,'').replace(/&/g,' and ').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');}
