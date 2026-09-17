load('crypto.js');
load('config.js');
function decryptContent(text) {
    text = String(text || "").trim(); if (!text) return "";
    try {
        let key=CryptoJS.enc.Utf8.parse("2bd40f62d20c1c49237a109d491974eb");
        let iv=CryptoJS.enc.Hex.parse(text.slice(0,32));
        let ciphertext=CryptoJS.enc.Hex.parse(text.slice(32));
        let params=CryptoJS.lib.CipherParams.create({ciphertext:ciphertext,formatter:CryptoJS.format.OpenSSL});
        return CryptoJS.AES.decrypt(params,key,{iv:iv}).toString(CryptoJS.enc.Utf8);
    } catch(e){ return ""; }
}
function execute(url) {
    let slug=getSlug(url); let m=String(url||"").match(/\/chuong-(\d+)/i); let num=m&&m[1]?m[1]:"";
    if(!slug||!num) return Response.error("V4 URL_INVALID");
    let endpoint=BASE_URL+"/api/reading/"+encodeURIComponent(slug)+"/chapters/"+encodeURIComponent(num)+"/content";
    let r=fetch(endpoint); if(!r.ok) return Response.error("V4 HTTP "+r.status);
    let content=decryptContent(r.text()); if(!content) return Response.error("V4 DECRYPT_EMPTY");
    if(content.indexOf("Đây là chương VIP")!==-1) return Response.error("V4 VIP_LOCKED");
    return Response.success('<p><b>[LOUIS V4]</b></p>'+content,"V4 · Chương "+num);
}
