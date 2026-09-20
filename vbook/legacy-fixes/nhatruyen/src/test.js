load('config.js');
function execute() {
    var url = "https://nhatruyen.site/truyen/van-co-than-de/chuong-1-tam-tram-nam-sau/";
    var doc = fetch(url).html();
    
    var divClasses = [];
    doc.select("div").forEach(function(el) {
        var cls = el.attr("class") + "";
        if (cls && cls.length > 0) {
            divClasses.push(cls);
        }
    });

    var hasIdReading = doc.select("#reading, #chapter-content").size() > 0;
    var contentEl = doc.select('.reading-content, .text-left, .nt-content').first();

    return Response.success({
        classes: divClasses.slice(0, 50),
        hasIdReading: hasIdReading + "",
        contentEl: contentEl ? "FOUND" : "NOT FOUND"
    });
}
