load('config.js');
var PROXY = 'https://tienvuc-vbook-proxy-louis.ducduy2411.workers.dev';
function execute(url) {
    var slug = getSlug(url);
    var m = String(url || '').match(/\/chuong-(\d+)/i);
    var num = m && m[1] ? m[1] : '';
    if (!slug || !num) return Response.error('V6 URL_INVALID');
    var endpoint = PROXY + '/chapter?slug=' + encodeURIComponent(slug) + '&num=' + encodeURIComponent(num);
    var r = fetch(endpoint);
    if (!r.ok) {
        if (r.status === 402) return Response.error('V6 VIP_LOCKED');
        return Response.error('V6 PROXY ' + r.status);
    }
    return Response.success(r.text(), 'V6 · Chương ' + num);
}