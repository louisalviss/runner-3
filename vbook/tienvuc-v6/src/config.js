let BASE_URL = "https://tienvuc.me";
let SYNTH_BASE = "https://louisalviss.github.io/vbook/tienvuc-v6";
try { if (DOMAIN) BASE_URL = String(DOMAIN).replace(/\/$/, ""); } catch (error) {}

function getSlug(url) {
    let s = String(url || "").split("?")[0].split("#")[0];
    let p = s.replace(/^https?:\/\/[^\/]+/i, "");
    let parts = p.split("/").filter(function(x){ return !!x; });
    if (parts.length >= 3 && parts[0] === "vbook" && parts[1] === "tienvuc-v6") return parts[2];
    return parts.length ? parts[0] : "";
}
function synthBookUrl(slug){ return SYNTH_BASE + "/" + slug; }
function synthChapUrl(slug,num){ return SYNTH_BASE + "/" + slug + "/chuong-" + num; }
function coverUrl(cover) {
    if (!cover) return "";
    if (cover.domain && cover.url) return String(cover.domain).replace(/\/$/, "") + "/" + String(cover.url).replace(/^\//, "");
    if (cover.noImg) return String(cover.noImg);
    return "";
}
function bookItem(book) {
    let vip = book && book.vip === true ? "【VIP】 " : "";
    let author = book && book.author && book.author.name ? String(book.author.name) : "";
    let slug = book && book.slug ? String(book.slug) : "";
    return {name: book && book.name ? String(book.name) : slug, link: synthBookUrl(slug), cover: coverUrl(book ? book.cover : null), description: vip + author, host: ""};
}
