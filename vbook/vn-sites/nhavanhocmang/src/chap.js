function execute(url){
    var r=fetch(url);
    if(!r.ok)return Response.error('HTTP '+r.status);
    var d=r.html(), es=d.select('script'), best='';
    for(var i=0;i<es.size();i++){
        var s=String(es.get(i).html()||es.get(i).text()||'');
        if(s.indexOf('self.__next_f.push(')<0)continue;
        var p=s.indexOf('self.__next_f.push(')+19;
        var q=s.lastIndexOf(')');
        if(q<=p)continue;
        try{
            var a=JSON.parse(s.substring(p,q));
            if(a&&a.length>1&&typeof a[1]==='string'){
                var v=a[1];
                if(v.indexOf('<p')>=0&&v.length>best.length)best=v;
            }
        }catch(e){}
    }
    if(best&&best.length>120)return Response.success(best);
    return Response.error('RSC_CONTENT_NOT_FOUND');
}
