load("config.js");
function execute(url) {
    try {
        var raw=String(url||'');
        var apiBase=BASE_URL.replace('https://','https://api.');
        var appBase=BASE_URL.replace(/\/$/,'')+'/';
        var apiRoot=apiBase.replace(/\/$/,'')+'/';
        var apiUrl;
        if(raw.indexOf(apiRoot)===0) apiUrl=raw;
        else if(raw.indexOf(appBase)===0) apiUrl=apiRoot+raw.substring(appBase.length);
        else apiUrl=apiRoot+raw.replace(/^\/+/, '');
        let response=fetch(apiUrl);
        if(!response.ok) return Response.error('HTTP '+response.status+' '+apiUrl);
        let json=response.json();
        if(!json || (!json.success && json.code!==0)) return Response.error('BAD_API '+JSON.stringify(json));
        if(!json.data || !Array.isArray(json.data)) return Response.error('NO_CHAPTERS');
        let chapters=[];
        json.data.forEach(e=>chapters.push({name:e.name,url:e.url,pay:e.is_vip||false,host:BASE_URL}));
        return Response.success(chapters);
    } catch(error) { return Response.error('TOC '+error.message); }
}
