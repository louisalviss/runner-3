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
    } catch (error) {
        return "";
    }
}

function execute(url) {
    url = normalizeUrl(url);
    let slug = getSlug(url);
    let match = url.match(/\/chuong-(\d+)/i);
    let num = match && match.length > 1 ? match[1] : "";
    if (!slug || !num) return Response.error("URL chương không hợp lệ");

    let endpoint = BASE_URL + "/api/reading/" + encodeURIComponent(slug) + "/chapters/" + encodeURIComponent(num) + "/content";
    let response = fetch(endpoint);
    if (!response.ok) return Response.error("HTTP " + response.status);
    let content = decryptContent(response.text());
    let locked = content.indexOf("Đây là chương VIP") !== -1;

    if (locked) {
        let auth = "";
        let browser = null;
        try {
            browser = Engine.newBrowser();
            browser.launch(url, 5000);
            browser.callJs("var a=window.localStorage.getItem('auth._token.local')||'';var x=document.createElement('vbookauth');x.textContent=a;document.body.appendChild(x);", 100);
            auth = browser.html().select("vbookauth").text();
        } catch (error) {
            auth = "";
        }
        try { if (browser) browser.close(); } catch (closeError) {}

        if (auth) {
            let paidResponse = fetch(endpoint, { method: "GET", headers: { Authorization: auth } });
            if (paidResponse.ok) {
                let paidContent = decryptContent(paidResponse.text());
                if (paidContent) content = paidContent;
            }
        }
    }

    if (!content) return Response.error("Không giải mã được nội dung chương");
    return Response.success(content, "Chương " + num);
}
