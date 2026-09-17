load('config.js');
var PROXY = 'https://tienvuc-vbook-proxy-louis.ducduy2411.workers.dev';
function getAuthToken() {
    var browser = null;
    var auth = '';
    try {
        browser = Engine.newBrowser();
        browser.launch(BASE_URL, 5000);
        browser.callJs("var t=window.localStorage.getItem('auth._token.local')||'';var e=document.createElement('vbookauth');e.textContent=t;document.body.appendChild(e);", 100);
        auth = browser.html().select('vbookauth').text();
    } catch (e) { auth = ''; }
    try { if (browser) browser.close(); } catch (e2) {}
    return auth;
}
function execute(url) {
    var slug = getSlug(url);
    var m = String(url || '').match(/\/chuong-(\d+)/i);
    var num = m && m[1] ? m[1] : '';
    if (!slug || !num) return Response.error('V7 URL_INVALID');
    var endpoint = PROXY + '/chapter?slug=' + encodeURIComponent(slug) + '&num=' + encodeURIComponent(num);
    var r = fetch(endpoint);
    if (r.ok) return Response.success(r.text(), 'V7 · Chương ' + num);
    if (r.status !== 402) return Response.error('V7 PROXY ' + r.status);
    var auth = getAuthToken();
    if (!auth) return Response.error('V7 VIP_LOGIN_REQUIRED');
    var paid = fetch(endpoint, { method: 'GET', headers: { Authorization: auth } });
    if (paid.ok) return Response.success(paid.text(), 'V7 VIP · Chương ' + num);
    if (paid.status === 401 || paid.status === 403) return Response.error('V7 SESSION_EXPIRED');
    if (paid.status === 402) return Response.error('V7 VIP_NOT_PURCHASED_OR_SESSION_EXPIRED');
    return Response.error('V7 VIP_PROXY ' + paid.status);
}
