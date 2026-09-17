load('crypto.js');
load('config.js');

function decryptContent(text) {
    text = String(text || "").trim();
    if (!text) return "";
    try {
        let key = CryptoJS.enc.Utf8.parse("2bd40f62d20c1c49237a109d491974eb");
        let iv = CryptoJS.enc.Hex.parse(text.slice(0, 32));
        let ciphertext = CryptoJS.enc.Hex.parse(text.slice(32));
        let params = CryptoJS.lib.CipherParams.create({ ciphertext: ciphertext, formatter: CryptoJS.format.OpenSSL });
        let decrypted = CryptoJS.AES.decrypt(params, key, { iv: iv });
        return decrypted.toString(CryptoJS.enc.Utf8);
    } catch (error) { return ""; }
}

function execute(url) {
    url = normalizeUrl(url);
    let slug = getSlug(url);
    let m = url.match(/\/chuong-(\d+)/i);
    let num = m && m[1] ? m[1] : "";
    if (!slug || !num) return Response.error("V3 URL_CHAPTER_INVALID");
    let endpoint = BASE_URL + "/api/reading/" + encodeURIComponent(slug) + "/chapters/" + encodeURIComponent(num) + "/content";
    let r = fetch(endpoint);
    if (!r.ok) return Response.error("V3 HTTP " + r.status);
    let content = decryptContent(r.text());
    if (!content) return Response.error("V3 DECRYPT_EMPTY");
    if (content.indexOf("Đây là chương VIP") !== -1) return Response.error("V3 VIP_LOCKED");
    return Response.success(content, "V3 · Chương " + num);
}
