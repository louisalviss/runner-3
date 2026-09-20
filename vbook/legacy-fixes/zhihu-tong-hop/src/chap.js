function execute(url) {
    if (url.indexOf("daotruyen.me") >= 0) return chapDaoTruyen(url);
    if (url.indexOf("ocuadua.com") >= 0) return chapOCuaDua(url);
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var html = "";
    if (url.indexOf("nguyetmongthu.com") >= 0 || String(response.url).indexOf("hubtruyen.net") >= 0) {
        html = doc.select("#chapter-content").html();
    } else if (url.indexOf("toctruyen.net") >= 0) {
        html = decodeTocTruyen(doc);
    } else if (url.indexOf("yeutruyen.me") >= 0) {
        html = doc.select(".reading").html();
    } else if (url.indexOf("nguyetlau.top") >= 0) {
        html = chapterNguyetLau(doc);
    } else if (url.indexOf("monkeydd.com") >= 0) {
        html = chapterMonkeyD(doc, url);
    } else if (url.indexOf("comong.info") >= 0) {
        html = doc.select(".story-content .page-description").html();
    } else {
        html = chapterGeneric(doc);
    }
    if (!html) return Response.error("Nội dung trống");
    return Response.success(cleanContent(html));
}

function chapterMonkeyD(doc, url) {
    var container = doc.select(".actac, .chapter-content .content-container").first();
    if (!container) return "";
    container.select(".actcl, .affClick, a[href*=shopee], img[src*=shopee], img[src*=click-here], img[src*=unlock], [onclick*=affLink], #affLink, .signature, .chapter-nav, .my-4").remove();
    var cssText = "";
    doc.select("style").forEach(function(item) { cssText += item.html() + "\n"; });
    doc.select("link[rel=stylesheet][href]").forEach(function(item) {
        var href = item.attr("href");
        if (!href) return;
        if (href.indexOf("//") === 0) href = "https:" + href;
        if (href.indexOf("http") !== 0) href = "https://www.monkeydd.com" + (href.charAt(0) === "/" ? href : "/" + href);
        try {
            var response = Http.get(href);
            if (response && response.string) cssText += response.string() + "\n";
        } catch (error) {}
    });
    var pseudoMap = {};
    var regex = /\.([\w-]+)::?before\s*\{[^}]*content:\s*["']([^"']*)["'][^}]*\}/gi;
    var match;
    while ((match = regex.exec(cssText)) !== null) pseudoMap[match[1]] = match[2];
    return container.html().replace(/<span\s+class="([^"]+)"[^>]*>\s*<\/span>/gi, function(all, classNames) {
        var classes = classNames.trim().split(/\s+/);
        for (var i = 0; i < classes.length; i++) {
            if (pseudoMap[classes[i]] !== undefined) return pseudoMap[classes[i]];
        }
        return "";
    });
}

function chapterGeneric(doc) {
    var container = doc.select(".chap-content, #chapContent, .chapter-content, div.reading-content, .reading-content, .actac, .content-container, .prose, [class*=prose], #chapter-content-render, #readerContent, .reading, .truyen").first();
    if (!container) return "";
    container.select("script, style, iframe, input, ins, .ads, .affClick, .signature, #text-chapter-toolbar, .chapter-nav, .w2w_read_more").remove();
    return container.html() || "";
}

function chapDaoTruyen(url) {
    var response = fetch(url, { headers: { "accept": "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36", "referer": "https://daotruyen.me/", "origin": "https://daotruyen.me" } });
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var html = json.chapter && json.chapter.paragraph ? json.chapter.paragraph : json.data || "";
    return html ? Response.success(cleanContent(html)) : Response.error("Nội dung trống");
}

function chapOCuaDua(url) {
    var match = String(url).match(/chapter=([A-Za-z0-9]+)/);
    if (!match) return Response.error("URL chương không hợp lệ");
    var response = fetch("https://doctruyen-be-ojbd.onrender.com/api/stories/" + match[1] + "/detail");
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    return json.content ? Response.success(cleanContent(json.content)) : Response.error("Nội dung trống");
}

function chapterNguyetLau(doc) {
    var raw = doc.select("div#app").attr("data-page");
    if (!raw) return "";
    raw = String(raw).replace(/&quot;/g, '"').replace(/&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    try {
        var page = JSON.parse(raw);
        var chapter = page.props && page.props.chapter;
        if (chapter && chapter.data) chapter = chapter.data;
        return chapter && chapter.content ? String(chapter.content) : "";
    } catch (error) {
        return "";
    }
}

function decodeTocTruyen(doc) {
    var container = doc.select("#chapter-content, .chapter-content, .novel-reading-content").first();
    if (!container) return "";
    var html = container.html();
    var css = doc.select("style").html() || "";
    var dict = {};
    var regex = /\.([a-zA-Z0-9_-]+):before\s*\{\s*content:\s*"([^"]?)"\s*;?\}/g;
    var match;
    while ((match = regex.exec(css))) dict[match[1]] = match[2];
    return html.replace(/<span class="([^"]+)"><\/span>/g, function(all, className) { return dict[className] || ""; });
}

function cleanContent(html) {
    var content = String(html).replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "").replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "").replace(/<iframe[^>]*>[\s\S]*?<\/iframe>/gi, "").replace(/<div[^>]*class="[^"]*w2w_read_more[^"]*"[^>]*>[\s\S]*?<\/div>/gi, "").replace(/<p[^>]*>\s*(?:&nbsp;|<br\s*\/?>\s*)*<\/p>/gi, "").replace(/<span[^>]*>\s*<\/span>/gi, "").replace(/ch\*t/gi, "chết").replace(/gi\*t/gi, "giết").replace(/(<br\s*\/?>\s*){3,}/gi, "<br><br>");
    return content.replace(/(^|>)([^<]*)(?=<|$)/g, function(all, prefix, text) {
        return prefix + cleanObfuscatedText(text);
    }).trim();
}

function cleanObfuscatedText(value) {
    var text = String(value || "");
    var previous = "";
    while (text !== previous) {
        previous = text;
        text = text.replace(/([0-9A-Za-zÀ-ỹĐđ])\s*\/{1,}\s*([0-9A-Za-zÀ-ỹĐđ])/g, "$1$2");
    }
    return text;
}
