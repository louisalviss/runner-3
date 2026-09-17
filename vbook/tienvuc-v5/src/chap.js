load('crypto.js');
load('config.js');
function getDecryptedCode(text) {
    var key = CryptoJS.enc.Utf8.parse('2bd40f62d20c1c49237a109d491974eb');
    var iv = CryptoJS.enc.Hex.parse(text.slice(0, 32));
    var ciphertext = CryptoJS.enc.Hex.parse(text.slice(32));
    var encryptedCP = CryptoJS.lib.CipherParams.create({ciphertext: ciphertext, formatter: CryptoJS.format.OpenSSL});
    var decryptedWA = CryptoJS.AES.decrypt(encryptedCP, key, {iv: iv});
    return decryptedWA.toString(CryptoJS.enc.Utf8);
}
function execute(url) {
    let slug = getSlug(url);
    let m = String(url || '').match(/\/chuong-(\d+)/i);
    let num = m && m[1] ? m[1] : '';
    if (!slug || !num) return Response.error('V5 URL_INVALID');
    let endpoint = BASE_URL + '/api/reading/' + encodeURIComponent(slug) + '/chapters/' + encodeURIComponent(num) + '/content';
    let r = fetch(endpoint);
    if (!r.ok) return Response.error('V5 HTTP ' + r.status);
    let content = getDecryptedCode(r.text());
    if (!content) return Response.error('V5 DECRYPT_EMPTY');
    if (content.indexOf('Đây là chương VIP') !== -1) return Response.error('V5 VIP_LOCKED');
    return Response.success('<p><b>[LOUIS V5]</b></p>' + content, 'V5 · Chương ' + num);
}