function execute(text, voice) {
    var voicePart = String(voice || '').split(';');
    var voiceName = voicePart[0] || 'vi-VN-HoaiMyNeural';
    var voiceGender = voicePart[1] || 'Female';
    var voiceLangPart = voiceName.split('-');
    var voiceLang = voiceLangPart.length >= 2 ? voiceLangPart[0] + '-' + voiceLangPart[1] : 'vi-VN';
    var tokenData = findBingData();
    if (!tokenData) return Response.error('BING_TOKEN_NOT_FOUND');
    var ssml = generateSSML(text, voiceLang, voiceName, voiceGender);
    var ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36';
    var response = fetch('https://www.bing.com/tfettts', {
        method: 'POST',
        queries: { isVertical: '1', IG: tokenData.IG, IID: tokenData.IID },
        headers: {
            'User-Agent': ua,
            'Referer': 'https://www.bing.com/translator',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'ssml=' + encodeURIComponent(ssml) + '&token=' + encodeURIComponent(tokenData.token) + '&key=' + encodeURIComponent(String(tokenData.key))
    });
    if (!response.ok) return Response.error('BING_TTS_HTTP_' + response.status);
    return Response.success(response.base64());
}

function findBingData() {
    var ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36';
    var res = fetch('https://www.bing.com/translator', {headers:{'User-Agent':ua,'Accept':'text/html,application/xhtml+xml'}});
    if (!res.ok) return null;
    var html = res.text();
    var m = /var params_AbusePreventionHelper\s*=\s*(\[.*?\]);/.exec(html);
    var ig = /IG:\"([A-Z0-9]+)\"/.exec(html);
    var iid = /data-iid=\"(translator\.\d+)\"/.exec(html);
    if (!m || !ig || !iid) return null;
    var jsonToken;
    try { jsonToken = JSON.parse(m[1]); } catch (e) { return null; }
    if (!jsonToken || jsonToken.length < 2) return null;
    return { IG:ig[1], IID:iid[1], token:jsonToken[1], key:jsonToken[0] };
}

function generateSSML(text, voiceLang, voiceName, voiceGender) {
    return "<speak version='1.0' xml:lang='" + voiceLang + "'><voice xml:lang='" + voiceLang + "' xml:gender='" + voiceGender + "' name='" + voiceName + "'>" + escapeXml(String(text || '')) + "</voice></speak>";
}
function escapeXml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&apos;');}
