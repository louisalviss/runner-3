function execute(url) {
    if (url.indexOf("daotruyen.me") >= 0) return detailDaoTruyen(url);
    if (url.indexOf("ocuadua.com") >= 0) return detailOCuaDua(url);
    if (url.indexOf("nguyetlau.top") >= 0) return detailNguyetLau(url);
    if (url.indexOf("truyendexuat.com") >= 0) return detailTruyenDeXuat(url);
    if (url.indexOf("monkeydd.com") >= 0) return detailMonkeyD(url);
    if (url.indexOf("mottruyen.top") >= 0) return detailMotTruyen(url);
    if (url.indexOf("toctruyen.net") >= 0) return detailTocTruyen(url);
    if (url.indexOf("tiemchungot.com") >= 0) return detailTiemChuNgot(url);
    if (url.indexOf("vanmonglau.com") >= 0) return detailVanMongLau(url);
    if (url.indexOf("comong.info") >= 0) return detailComongInfo(url);
    if (isBootstrapSource(url)) return detailBootstrap(url);
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    return detailHtml(response.html(), url);
}

function detailComongInfo(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var info = doc.select(".info").first();
    var author = info ? cleanText(info.select("a[href*='/tac_gia/']").text()) : "";
    var genres = [];
    if (info) info.select("a[href*='/category/']").forEach(function(item) {
        var title = cleanText(item.text());
        var href = item.attr("href");
        if (title && href) genres.push({ title: title, input: "comonginfo|" + href, script: "gen_other.js" });
    });
    var name = cleanText(doc.select("h1").first().text());
    var description = doc.select('meta[property="og:description"]').attr("content") || "";
    return Response.success({
        name: name,
        cover: firstImage(doc, ".wp-post-image, meta[property=og:image]"),
        host: "https://comong.info",
        author: author,
        description: cleanHtml(description),
        detail: "Tác giả: " + author + (genres.length ? "<br>Thể loại: " + genreTitles(genres).join(", ") : "") + "<br>Trạng thái: Hoàn thành",
        genres: genres,
        ongoing: false
    });
}

function isBootstrapSource(url) {
    return /(?:comong\.site|doctruyen\.shop|doctruyenchill\.net|nangtho\.site|saytruyen\.vn|yeungontinh\.site|truyentv\.site)/.test(url);
}

function detailBootstrap(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var host = getHost(url);
    var authorItem = doc.select(".story-detail__bottom--info p.mb-1 a.hover-title").first();
    var author = authorItem ? authorItem.text().trim() : "";
    var book = findJsonLd(doc, "Book");
    var bookAuthor = book.author && typeof book.author === "object" ? book.author.name || "" : book.author || "";
    if (!author || author === cleanText(doc.select(".story-detail__top .story-name").text())) author = cleanText(bookAuthor);
    var status = doc.select("p.mb-1 .text-info").text().trim();
    var genres = [];
    doc.select(".story-detail__bottom--info a.hover-title.me-1").forEach(function(item) {
        var title = cleanText(item.text().replace(/,$/, ""));
        var href = absoluteUrl(host, item.attr("href"));
        if (title && href) genres.push({ title: title, input: genreInput(url, href), script: "gen_other.js" });
    });
    var detail = (author ? "Tác giả: " + author : "") + (genres.length ? (author ? "<br>" : "") + "Thể loại: " + genreTitles(genres).join(", ") : "") + (status ? ((author || genres.length) ? "<br>" : "") + "Trạng thái: " + status : "");
    return Response.success({ name: cleanText(doc.select(".story-detail__top .story-name").text()), cover: absoluteUrl(host, firstImage(doc, ".story-detail__top--image img")), host: host, author: author, description: cleanHtml(firstHtml(doc, ".story-detail__top--desc")), detail: detail, genres: genres.length ? genres : undefined, ongoing: !/(hoàn thành|trọn bộ|full|đã đủ bộ)/i.test(status) });
}

function detailTiemChuNgot(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var status = firstText(doc, ".detail-hero .badge-soft");
    var stats = firstText(doc, ".detail-stats");
    var genres = [];
    doc.select("a.cate-item[itemprop=genre]").forEach(function(item) { var title = cleanText(item.text()); var href = absoluteUrl("https://tiemchungot.com", item.attr("href")); if (title && href) genres.push({ title: title, input: "tiemchungot|" + href, script: "gen_other.js" }); });
    return Response.success({ name: cleanText(firstText(doc, "h1.detail-title")), cover: absoluteUrl("https://tiemchungot.com", firstImage(doc, ".detail-cover img.story-image")), host: "https://tiemchungot.com", author: "Chưa xác định", description: cleanHtml(firstHtml(doc, ".detail-desc")), detail: "Trạng thái: " + status + (stats ? "<br>" + stats : ""), ongoing: status.toUpperCase().indexOf("FULL") < 0, genres: genres.length ? genres : undefined });
}

function detailVanMongLau(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var author = "Đang cập nhật", status = "", translator = "";
    doc.select("div.grid div.flex.items-center").forEach(function(item) {
        var label = item.select("span.text-gray-400").text().trim();
        var value = item.select("span").last().text().trim();
        if (label.indexOf("Tác giả") >= 0) author = value;
        else if (label.indexOf("Trạng thái") >= 0) status = value;
        else if (label.indexOf("Dịch Giả") >= 0) translator = value;
    });
    var description = doc.select("div.mb-6 > p").html() || "";
    var detail = "Tác giả: " + author + (translator ? "<br>Dịch giả: " + translator : "") + (status ? "<br>Trạng thái: " + status : "");
    return Response.success({ name: cleanText(doc.select("h1.text-4xl").text()), cover: absoluteUrl("https://vanmonglau.com", doc.select("img[alt]").attr("src") || ""), author: author, host: "https://vanmonglau.com", description: cleanHtml(description), detail: detail, ongoing: !/(hoàn thành|trọn bộ|full)/i.test(status) });
}

function detailMotTruyen(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var article = findJsonLd(doc, "Article");
    var name = article.headline || firstText(doc, "h1[itemprop=name], h1");
    var author = article.author && typeof article.author === "object" ? article.author.name || "" : article.author || "";
    var image = article.image;
    if (image && typeof image !== "string") image = image[0] || image.url || "";
    var status = firstText(doc, "[itemprop=bookFormat]");
    var count = firstText(doc, "[itemprop=numberOfPages]");
    var genres = [];
    doc.select("a[href^='/the-loai/']").forEach(function(item) {
        var title = cleanText(item.text());
        var href = absoluteUrl("https://mottruyen.top", item.attr("href"));
        if (title && href) genres.push({ title: title, input: "mottruyen|" + href, script: "gen_other.js" });
    });
    var lines = [];
    if (author) lines.push("Tác giả: " + author);
    if (status) lines.push("Trạng thái: " + status);
    if (count) lines.push("Số chương: " + count);
    return Response.success({ name: cleanText(name), cover: absoluteUrl("https://mottruyen.top", image || firstImage(doc, "article img[itemprop=image]")), author: cleanText(author), description: cleanHtml(article.description || firstHtml(doc, "[itemprop=description]")), detail: lines.join("<br>"), host: "https://mottruyen.top", ongoing: status.indexOf("Đã hoàn thành") < 0, genres: genres.length ? genres : undefined });
}

function detailTocTruyen(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    function info(label) { return cleanText(doc.select("div.novel-info-card .tr:contains(" + label + ") .td").text()); }
    var author = info("Tác giả");
    var poster = cleanText(doc.select("div.novel-info-card .tr:contains(Người đăng) a").text());
    var status = info("Trạng thái");
    var total = info("Số chương dự kiến");
    var views = cleanText(doc.select("#novel-view").text());
    var genres = collectGenres(doc, url);
    var latest = cleanText(doc.select("div.novel-body .fv-button.fv-danger + span").text());
    var updated = cleanText(doc.select("section:has(#description) h4.header-sub").first().text());
    var detail = "Tác giả: " + author + "<br>Người đăng: " + poster + "<br>Tình trạng: " + status + "<br>Tổng chương: " + total + (latest ? "<br>Chương mới nhất: " + latest : "") + "<br>Cập nhật: " + updated + "<br>Lượt đọc: " + views;
    return Response.success({ name: cleanText(doc.select("div.novel-header h1").text()), cover: absoluteUrl("https://toctruyen.net", doc.select("div.novel-header .novel-thumb").attr("data-original")), author: author, poster: poster, status: status, genres: genres, description: cleanHtml(firstHtml(doc, "#description")), detail: detail, host: "https://toctruyen.net", ongoing: !/(hoàn thành|trọn bộ|full)/i.test(status) });
}

function detailMonkeyD(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var cssMap = {};
    doc.select("style").forEach(function(style) {
        var css = style.html() + "";
        var regex = /\.([a-z0-9\-]+)::?before\s*\{[^}]*content:\s*"([^"]*)"[^}]*\}/gi;
        var match;
        while ((match = regex.exec(css)) !== null) cssMap[match[1]] = match[2];
    });
    var description = doc.select(".ql-editor").html() || "";
    description = description.replace(/<span class="([^"]+)"[^>]*>\s*<\/span>/gi, function(all, names) {
        var classes = names.split(/\s+/);
        for (var i = 0; i < classes.length; i++) if (cssMap[classes[i]] !== undefined) return cssMap[classes[i]];
        return "";
    });
    description = cleanHtml(description).replace(/<span[^>]*>\s*<\/span>/gi, "");
    var genres = [];
    doc.select(".col-sm-9 a").forEach(function(item) {
        var title = cleanText(item.text());
        var href = item.attr("href");
        if (title && href) genres.push({ title: title, input: href.replace(/^https?:\/\/(?:www\.)?monkeydd\.com\//, "").replace(/\.html$/, ""), script: "gen_monkeyd.js" });
    });
    var team = dtValue(doc, "Team");
    var author = dtValue(doc, "Tác giả");
    var views = dtValue(doc, "Lượt xem");
    var favorites = dtValue(doc, "Yêu thích");
    var follows = dtValue(doc, "Lượt theo dõi");
    var status = dtValue(doc, "Trạng thái");
    var updated = dtValue(doc, "Cập nhật");
    var type = dtValue(doc, "Loại");
    var detail = "Team: " + team + "<br>Tác giả: " + author + "<br>Lượt xem: " + views + "<br>Yêu thích: " + favorites + "<br>Lượt theo dõi: " + follows + "<br>Trạng thái: " + status + "<br>Cập nhật: " + updated + "<br>Loại: " + type;
    return Response.success({ name: cleanText(doc.select("h1").text()), cover: firstImage(doc, "meta[property=og:image]"), description: description, author: author, detail: detail, genres: genres, ongoing: status.indexOf("Đang phát hành") >= 0, host: "https://www.monkeydd.com" });
}

function detailHtml(doc, url) {
    var host = getHost(url);
    var name = firstText(doc, "h1.story-name, h1.entry-title, .story-detail-title, .story-detail__top .story-name, .fs-3, div.post-title h1, div.novel-header h1, h1.detail-title, h1 a.title-truyen, h1");
    if (!name) name = doc.select('meta[property="og:title"]').attr("content") || "";
    name = cleanText(name.replace(/\s*[-–|]\s*(?:MonkeyD|Bạch Ngọc Lâu|Đọc Truyện.*|Yêu Truyện).*$/i, ""));

    var cover = firstImage(doc, ".story-detail__top--image img, .story-thumb img, .story-cover-image img, div.summary_image img, div.novel-header .novel-thumb, .detail-cover img.story-image, .image-truyen img, meta[property=og:image], meta[property=og:image:secure_url]");
    cover = absoluteUrl(host, cover);

    var author = dtValue(doc, "Tác giả") || infoValue(doc, "Tác giả");
    if (!author) author = infoValue(doc, "Team");
    if (!author) author = infoValue(doc, "Nhóm dịch");
    if (!author) author = firstText(doc, ".story-author, [itemprop=author], meta[property=og:novel:author]");
    author = cleanText(author.replace(/^Tác giả:\s*/i, ""));

    var status = dtValue(doc, "Trạng thái") || infoValue(doc, "Trạng thái") || infoValue(doc, "Tình trạng");
    if (!status) status = firstText(doc, ".badge-soft, p.mb-1 .text-info");
    var translator = infoValue(doc, "Nhà dịch") || infoValue(doc, "Dịch Giả");
    var views = dtValue(doc, "Lượt xem") || infoValue(doc, "Lượt xem");
    var chapterInfo = dtValue(doc, "Số chương") || infoValue(doc, "Số chương");
    var updated = dtValue(doc, "Cập nhật");
    var type = dtValue(doc, "Loại");

    var genres = collectGenres(doc, url);
    var description = firstHtml(doc, ".story-detail__top--desc, .story-short-desc, #manga-description, .story-description-text, .description-summary .summary__content, #description, .detail-desc, .noi-dung, .ql-editor, div.mb-6 > p, div.mb-6");
    if (!description) description = doc.select('meta[property="og:description"]').attr("content") || "";
    description = cleanHtml(decodePseudoContent(doc, description));

    var lines = [];
    if (author) lines.push("Tác giả: " + author);
    if (translator) lines.push("Dịch giả: " + cleanText(translator));
    if (genres.length) lines.push("Thể loại: " + genreTitles(genres).join(", "));
    if (status) lines.push("Trạng thái: " + cleanText(status));
    if (chapterInfo) lines.push("Số chương: " + cleanText(chapterInfo));
    if (views) lines.push("Lượt xem: " + cleanText(views));
    if (updated) lines.push("Cập nhật: " + cleanText(updated));
    if (type) lines.push("Loại: " + cleanText(type));

    return Response.success({
        name: name, cover: cover, host: host, author: author,
        description: description, detail: lines.join("<br>"),
        genres: genres.length ? genres : undefined,
        ongoing: !/(hoàn thành|trọn bộ|full|đã đủ bộ)/i.test(status)
    });
}

function detailTruyenDeXuat(url) {
    var response = fetch(url);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var doc = response.html();
    var name = firstText(doc, ".story-detail-title") || doc.select("meta[property=og:title]").attr("content") || "";
    var cover = firstImage(doc, ".story-cover-image img, meta[property=og:image], meta[property=og:image:secure_url]");
    var author = firstText(doc, ".story-detail-meta .story-meta-item:has(.fa-user-edit) .meta-value");
    var status = firstText(doc, ".story-detail-meta .story-meta-item:has(.fa-check-circle) .meta-value");
    var chapters = firstText(doc, ".story-detail-meta .story-meta-item:has(.fa-list-ol) .meta-value");
    var views = firstText(doc, ".story-detail-meta .story-meta-item:has(.fa-eye) .meta-value");
    var updated = doc.select("meta[property=article:modified_time]").attr("content") || "";
    var genres = collectGenres(doc, url);
    var description = firstHtml(doc, "#manga-description, .story-description-text") || doc.select("meta[property=og:description]").attr("content") || "";
    var detail = "Tác giả: " + author + "<br>Thể loại: " + genreTitles(genres).join(", ") + "<br>Trạng thái: " + status + "<br>Số chương: " + chapters + "<br>Lượt xem: " + views + "<br>Cập nhật: " + updated;
    return Response.success({ name: cleanText(name), cover: absoluteUrl("https://truyendexuat.com", cover), host: "https://truyendexuat.com", author: cleanText(author), description: cleanHtml(description), detail: detail, genres: genres.length ? genres : undefined, ongoing: !/(hoàn thành|trọn bộ|full)/i.test(status) });
}

function detailDaoTruyen(url) {
    if (url.indexOf("/api/public/v2/") < 0) url = "https://daotruyen.me/api/public/v2/" + url.replace(/\/$/, "").split("/").pop();
    var response = fetch(url, { headers: daoHeaders() });
    if (!response.ok) return Response.error("HTTP " + response.status);
    var json = response.json();
    var story = json.story;
    if (!story) return Response.error("Không có dữ liệu truyện");
    var categories = json.categories || [];
    var genres = [];
    for (var i = 0; i < categories.length; i++) {
        genres.push({ title: categories[i].categoryName, input: "/api/public/v2/stories-by-category/" + categories[i].id + "?pageNo=0&pageSize=20", script: "gen_daotruyen.js" });
    }
    var translate = json.translate || {};
    var cover = absoluteUrl("https://daotruyen.me", story.image || "");
    var detail = "Cập nhật: " + (json.elapsed || "Không rõ") + "<br>Tác giả: " + (story.authorName || "Không rõ") + "<br>Lượt xem: " + (story.totalView || 0) + "<br>Team: " + (translate.teamName || "Không rõ") + "<br>Trạng thái: " + (story.state === 1 ? "Đang ra" : "Trọn bộ");
    return Response.success({ name: cleanText(story.name), cover: cover, author: story.authorName || "", description: cleanHtml(story.description || ""), detail: detail, genres: genres, ongoing: story.state === 1, host: "https://daotruyen.me" });
}

function detailOCuaDua(url) {
    var match = String(url).match(/\/story\/([A-Za-z0-9-]+)/);
    if (!match) return Response.error("URL không hợp lệ");
    var response = fetch("https://doctruyen-be-ojbd.onrender.com/api/story/" + match[1]);
    if (!response.ok) return Response.error("HTTP " + response.status);
    var item = response.json();
    item = item.data || item;
    var author = item.author && item.author.name ? item.author.name : "Không rõ";
    var total = typeof item.totalChapters === "number" ? item.totalChapters : item.chapters instanceof Array ? item.chapters.length : 0;
    var cover = item.coverImage || "";
    if (cover.indexOf("https://cdn.jsdelivr.net/gh/") === 0) cover = cover.replace(/^https:\/\/cdn\.jsdelivr\.net\/gh\/([^/]+)\/([^/@]+)@([^/]+)\//, "https://raw.githubusercontent.com/$1/$2/$3/");
    return Response.success({ name: cleanText(item.title || ""), cover: absoluteUrl("https://ocuadua.com", cover), author: author, description: cleanHtml(item.description || ""), detail: "Người đăng: " + author + "<br>Tổng số chương: " + total, host: "https://ocuadua.com" });
}

function detailNguyetLau(url) {
    var response = fetch(url, { headers: { "Accept": "text/html", "User-Agent": "Mozilla/5.0" } });
    if (!response.ok) return Response.error("HTTP " + response.status);
    var raw = response.html().select("div#app").attr("data-page");
    if (!raw) return Response.error("Không đọc được Nguyệt Lâu");
    raw = decodeEntities(raw);
    try {
        var page = JSON.parse(raw);
        var novel = page.props && page.props.novel;
        if (novel && novel.data) novel = novel.data;
        if (!novel) return Response.error("Không có dữ liệu truyện");
        var author = novel.author && novel.author.name ? String(novel.author.name) : novel.author_name || "";
        var categoryNames = [];
        var categories = novel.categories || [];
        for (var i = 0; i < categories.length; i++) {
            var item = categories[i] && categories[i].data ? categories[i].data : categories[i];
            if (item && item.name) categoryNames.push(cleanText(item.name));
        }
        var status = String(novel.status || "");
        var statusText = status.indexOf("completed") >= 0 ? "Hoàn thành" : status || "Đang cập nhật";
        var latest = novel.latest_chapter && (novel.latest_chapter.title || novel.latest_chapter.name || novel.latest_chapter.chapter_number) || "";
        var detail = "Tác giả: " + author + "<br>Thể loại: " + categoryNames.join(", ") + "<br>Trạng thái: " + statusText + (latest ? "<br>Chương mới: " + latest : "");
        return Response.success({ name: cleanText(novel.title || ""), cover: absoluteUrl("https://nguyetlau.top/storage", novel.cover_image || ""), author: author, description: cleanText(novel.description || ""), detail: detail, ongoing: status.indexOf("completed") < 0 && statusText.indexOf("Hoàn") < 0, host: "https://nguyetlau.top" });
    } catch (error) { return Response.error("JSON Nguyệt Lâu không hợp lệ"); }
}

function infoValue(doc, label) {
    var selectors = [
        ".story-terms-group .flex-fill", ".story-detail__bottom--info p", ".post-content_item",
        "div.novel-info-card .tr", "dl.row", ".detail-stats", "ul.info-truyen li", "div.grid div.flex.items-center"
    ];
    for (var s = 0; s < selectors.length; s++) {
        var items = doc.select(selectors[s]);
        for (var i = 0; i < items.size(); i++) {
            var item = items.get(i);
            var text = item.text().replace(/\s+/g, " ").trim();
            if (text.toLowerCase().indexOf(label.toLowerCase()) < 0) continue;
            var value = item.select("a, .mt-4, .summary-content, .td, dd, .meta-value, span").last().text().trim();
            if (!value || value.toLowerCase() === label.toLowerCase()) value = text.replace(new RegExp("^.*?" + label + "\\s*:?\\s*", "i"), "");
            return value.trim();
        }
    }
    return "";
}

function dtValue(doc, label) {
    var item = doc.select("dt:contains(" + label + ") + dd").first();
    return item ? item.text().replace(/\s+/g, " ").trim() : "";
}

function collectGenres(doc, url) {
    var result = [];
    var seen = {};
    var selector = ".genres-content a, .story-categories a, .story-detail__bottom--info a[href*='/the-loai/'], .detail-genres a, #genre-tags a, .story-detail-tags a[href*='/the-loai/'], .row .col-sm-9 a[href*='/the-loai/'], .row .col-sm-9 a[href*='/nhom-dich/'], .info-truyen a[rel='category tag']";
    var links = doc.select(selector);
    for (var i = 0; i < links.size(); i++) {
        var item = links.get(i);
        var title = cleanText(item.text());
        var href = absoluteUrl(getHost(url), item.attr("href"));
        if (!title || !href || seen[title]) continue;
        seen[title] = true;
        result.push({ title: title, input: genreInput(url, href), script: genreScript(url) });
    }
    return result;
}

function genreScript(url) {
    if (url.indexOf("toctruyen.net") >= 0) return "gen_toctruyen.js";
    if (url.indexOf("monkeydd.com") >= 0) return "gen_monkeyd.js";
    if (url.indexOf("nguyetmongthu.com") >= 0) return "gen_nguyetmongthu.js";
    if (url.indexOf("yeutruyen.me") >= 0) return "gen_yeutruyen.js";
    if (url.indexOf("nguyetlau.top") >= 0) return "gen_nguyetlau.js";
    return "gen_other.js";
}

function genreInput(url, href) {
    var map = [["bachngoclau.com","bachngoclau"],["comong.site","comong"],["doctruyen.shop","doctruyen"],["doctruyenchill.net","doctruyenchill"],["laophatgia","laophatgia"],["metruyen.fit","metruyen"],["mottruyen.top","mottruyen"],["nangtho.site","nangtho"],["otruyen.online","otruyen"],["saytruyen.vn","saytruyen"],["yeungontinh.site","tanmong"],["tiemchungot.com","tiemchungot"],["tieuhoadan.com","tieuhoadan"],["truyendexuat.com","truyendexuat"],["truyentv.site","truyentv"],["vanmonglau.com","vanmonglau"],["vivutruyen.net","vivutruyen"]];
    for (var i = 0; i < map.length; i++) if (url.indexOf(map[i][0]) >= 0) return map[i][1] + "|" + href;
    return href;
}

function firstText(doc, selector) { var parts = selector.split(","); for (var i = 0; i < parts.length; i++) { var item = doc.select(parts[i].trim()).first(); if (item) { var value = (item.attr("content") || item.text() || "").trim(); if (value) return value; } } return ""; }
function firstHtml(doc, selector) { var parts = selector.split(","); for (var i = 0; i < parts.length; i++) { var item = doc.select(parts[i].trim()).first(); if (item && item.html()) return item.html(); } return ""; }
function firstImage(doc, selector) { var parts = selector.split(","); for (var i = 0; i < parts.length; i++) { var item = doc.select(parts[i].trim()).first(); if (item) { var value = item.attr("data-src") || item.attr("data-original") || item.attr("src") || item.attr("content") || ""; if (value && value.indexOf("data:image/") !== 0) return value; } } return ""; }
function genreTitles(genres) { var data = []; for (var i = 0; i < genres.length; i++) data.push(genres[i].title); return data; }
function findJsonLd(doc, type) {
    var scripts = doc.select('script[type="application/ld+json"]');
    for (var i = 0; i < scripts.size(); i++) {
        try {
            var value = JSON.parse(scripts.get(i).html());
            var items = value && value['@graph'] ? value['@graph'] : value instanceof Array ? value : [value];
            for (var j = 0; j < items.length; j++) if (items[j] && String(items[j]['@type']).indexOf(type) >= 0) return items[j];
        } catch (error) {}
    }
    return {};
}
function decodePseudoContent(doc, html) {
    var map = {};
    var css = "";
    doc.select("style").forEach(function(item) { css += item.html() + "\n"; });
    var regex = /\.([a-z0-9_-]+)::?before\s*\{[^}]*content:\s*["']([^"']*)["'][^}]*\}/gi;
    var match;
    while ((match = regex.exec(css)) !== null) map[match[1]] = match[2];
    return String(html || "").replace(/<span\s+class="([^"]+)"[^>]*>\s*<\/span>/gi, function(all, names) {
        var classes = names.split(/\s+/);
        for (var i = 0; i < classes.length; i++) if (map[classes[i]] !== undefined) return map[classes[i]];
        return "";
    });
}
function getHost(url) { var match = String(url).match(/^https?:\/\/[^/]+/); return match ? match[0] : ""; }
function absoluteUrl(host, value) { var url = String(value || "").trim(); if (!url || url.indexOf("data:image/") === 0) return ""; if (url.indexOf("//") === 0) return "https:" + url; if (url.indexOf("http") === 0) return url; url = url.replace(/^(?:\.\.\/)+/, ""); return host.replace(/\/$/, "") + "/" + url.replace(/^\//, ""); }
function decodeEntities(value) { return String(value || "").replace(/&quot;|&#34;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"); }
function daoHeaders() { return { "accept": "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 Chrome/119.0.0.0", "referer": "https://daotruyen.me/", "origin": "https://daotruyen.me" }; }

function cleanText(value) {
    var text = String(value || "").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ");
    var previous = "";
    while (text !== previous) { previous = text; text = text.replace(/([0-9A-Za-zÀ-ỹĐđ])\s*[\/_]+\s*([0-9A-Za-zÀ-ỹĐđ])/g, "$1$2").replace(/([a-zà-ỹđ])\.([a-zà-ỹđ])/g, "$1$2"); }
    return text.replace(/\s+/g, " ").trim();
}

function cleanHtml(value) {
    var html = String(value || "").replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "").replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "").replace(/<iframe[^>]*>[\s\S]*?<\/iframe>/gi, "").replace(/<input[^>]*>/gi, "").replace(/<p[^>]*>\s*(?:&nbsp;|<br\s*\/?>\s*)*<\/p>/gi, "").replace(/ch\*t/gi, "chết").replace(/gi\*t/gi, "giết");
    return html.replace(/(^|>)([^<]*)(?=<|$)/g, function(all, prefix, text) { return prefix + cleanText(text); }).trim();
}
