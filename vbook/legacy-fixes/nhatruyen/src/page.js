load('config.js');

// page.js - returns list of page URLs for TOC pagination
function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:www\.)?([^\/]+)/, BASE_URL);
    
    var response = fetch(url);
    if (!response.ok) return Response.error("Cannot load");
    
    var doc = response.html();
    
    // Extract parentId (post ID) from body class or article ID
    var parentId = null;
    var body = doc.select("body").first();
    if (body) {
        var match = body.attr("class").match(/postid-(\d+)/);
        if (match) parentId = match[1];
    }
    
    if (!parentId) {
        var article = doc.select("article[id*=post-]").first();
        if (article) {
            var match = article.attr("id").match(/post-(\d+)/);
            if (match) parentId = match[1];
        }
    }
    
    if (!parentId) {
        // Last resort: search raw text for postid-
        var htmlText = response.text();
        var match = htmlText.match(/postid-(\d+)/) || htmlText.match(/post-(\d+)/);
        if (match) parentId = match[1];
    }
    
    if (!parentId) {
        return Response.error("Cannot find parentId");
    }
    
    // Extract total number of pages
    var lastPage = 1;
    var jumpInput = doc.select("#nt-jump-input").first();
    if (jumpInput) {
        lastPage = parseInt(jumpInput.attr("max")) || 1;
    } else {
        // Fallback: look through pagination links
        doc.select(".nt-pagination a").forEach(function(el) {
            var onclick = el.attr("onclick") || "";
            var match = onclick.match(/loadChapters\((\d+)\)/);
            if (match) {
                var p = parseInt(match[1]);
                if (p > lastPage) lastPage = p;
            }
            // Also check text content in case it's a simple number link
            var pText = parseInt(el.text());
            if (!isNaN(pText) && pText > lastPage) lastPage = pText;
        });
    }
    
    // Return API URLs for each page
    var pages = [];
    for (var i = 1; i <= lastPage; i++) {
        pages.push(BASE_URL + "/wp-admin/admin-ajax.php?page=" + i + "&parent_id=" + parentId);
    }
    
    return Response.success(pages);
}