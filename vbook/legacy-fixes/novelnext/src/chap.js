load('config.js');
function execute(url) {
    var response = fetch(toUrl(url));
    if (response.ok) {
        var doc = response.html();
        doc.select("noscript").remove();
        doc.select("script").remove();
        doc.select("iframe").remove();
        doc.select("div.ads-responsive").remove();
        doc.select("[style=font-size.0px;]").remove();
        doc.select("a").remove();
        doc.select("#pf-3033-1").remove();
        doc.select("h4").remove();
        var txt = doc.select("#chr-content, .chapter .chr-c").html();
        return Response.success(txt);
    }
    return null;
}
