function latestChapterDescription(value) {
    var text = String(value || "").replace(/\s+/g, " ").trim();
    var match = text.match(/chương\s+([^\s|•,]+)/i);
    if (!match) return "";
    return "Chương " + match[1].replace(/[.:;]+$/, "");
}
