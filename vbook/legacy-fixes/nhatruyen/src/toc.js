load('config.js');

function execute(url) {
    url = url.replace(/^(?:https?:\/\/)?(?:www\.)?([^\/]+)/, BASE_URL);
    
    var parentId = null;
    var pageNum = 1;
    
    // Check if URL is an API URL from page.js
    if (url.indexOf("admin-ajax.php") > -1) {
        var parentMatch = url.match(/parent_id=(\d+)/);
        var pageMatch = url.match(/page=(\d+)/);
        parentId = parentMatch ? parentMatch[1] : null;
        pageNum = pageMatch ? parseInt(pageMatch[1]) : 1;
    } else {
        // Get parent_id from detail page
        var detailResponse = fetch(url);
        if (!detailResponse.ok) return Response.error("Cannot load: " + detailResponse.status);
        
        var doc = detailResponse.text();
        var match = doc.match(/postid-(\d+)/);
        parentId = match ? match[1] : null;
        
        if (!parentId) {
            return Response.error("Cannot find parent_id");
        }
    }
    
    var allChapters = [];
    var page = pageNum;
    var hasMore = true;
    var isApiCall = (url.indexOf("admin-ajax.php") > -1);
    
    while (hasMore) {
        var apiBody = "action=nt_load_chapters&parent_id=" + parentId + "&page=" + page;
        
        var apiResponse = fetch(BASE_URL + "/wp-admin/admin-ajax.php", {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest"
            },
            body: apiBody
        });
        
        if (!apiResponse.ok) break;
        
        var apiHtml = apiResponse.html();
        
        if (apiHtml.length < 50) {
            hasMore = false;
            break;
        }
        
        apiHtml.select("a[href]").forEach(function(el) {
            var text = (el.text() || "").trim();
            var href = (el.attr("href") || "").trim();
            
            if (text.indexOf("Chương") > -1 && href.indexOf("/chuong-") > -1) {
                allChapters.push({
                    name: text,
                    url: href,
                    host: BASE_URL
                });
            }
        });
        
        // If called from page.js (API URL), only fetch the given page
        if (isApiCall) {
            hasMore = false;
        } else if (apiHtml.indexOf("loadChapters(" + (page + 1) + ")") === -1) {
            hasMore = false;
        } else {
            page++;
        }
        
        if (page > 50) break;
    }
    
    if (allChapters.length === 0) {
        return Response.error("No chapters found");
    }
    
    var seenUrls = {};
    var uniqueChapters = [];
    for (var i = 0; i < allChapters.length; i++) {
        var c = allChapters[i];
        if (!seenUrls[c.url]) {
            seenUrls[c.url] = true;
            uniqueChapters.push(c);
        }
    }
    
    uniqueChapters.sort(function(a, b) {
        var numA = a.name.match(/Chương\s*(\d+)/);
        var numB = b.name.match(/Chương\s*(\d+)/);
        var nA = numA ? parseInt(numA[1]) : 0;
        var nB = numB ? parseInt(numB[1]) : 0;
        return nA - nB;
    });
    
    return Response.success(uniqueChapters);
}