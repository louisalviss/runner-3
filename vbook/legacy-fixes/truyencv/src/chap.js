load('md5.js');
function execute(url) {
    let chapterId = /chapter_id=(\d+)$/.exec(url)[1];
    let time = Math.floor(Date.now() / 1000);
    let sig = md5("0.jD95wSNRZQ." + time + "." + chapterId);
    let response = fetch("http://api.mottruyen.com/chapter/?userid=0&sig=" + sig + "&time=" + time + "&chapter_id=" + chapterId + "&os=android&app_version=1.0.6");
    if (response.ok) {
        let json = response.json();
        return Response.success(json.data.CONTENT.replace("Người đăng: " + json.data.UNAME, ""));
    }
    return null;
}