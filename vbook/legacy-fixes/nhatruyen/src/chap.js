load('config.js');

function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:[^@\n]+@)?(?:www\.)?([^:\/\n?]+)/img, BASE_URL);
    var response = fetch(url);
    if (response.ok) {
        var doc = response.html();
        var content = doc.select('.chapter-content, .entry-content, .reading-content, .text-left, .nt-content').first();
        if (content) {
            // Clean up
            content.select('script, style, ins, .adsbygoogle, .nt-msg, .nt-nav').remove();
            return Response.success(content.html() + "");
        }
    }
    return Response.error('Failed to load chapter content');
}
