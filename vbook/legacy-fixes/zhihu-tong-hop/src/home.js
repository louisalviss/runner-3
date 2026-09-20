function execute() {
    return Response.success([
        { title: "Toctruyen", input: "/tim-kiem.html", script: "gen_toctruyen.js" },
        { title: "Đảo Truyện", input: "/api/public/stories", script: "gen_daotruyen.js" },
        { title: "MonkeyD", input: "truyen-moi", script: "gen_monkeyd.js" },
        { title: "Mọt Truyện", input: "mottruyen|https://mottruyen.top/danh-sach/truyen-moi", script: "gen_other.js" },         
        { title: "Nguyệt Mộng Thư", input: "/truyen/", script: "gen_nguyetmongthu.js" },
        { title: "Yêu Truyện", input: "https://yeutruyen.me/moi-cap-nhat/", script: "gen_yeutruyen.js" },
        { title: "Nguyệt Lâu", input: "/novels?sort=latest_chapter", script: "gen_nguyetlau.js" },
        { title: "Bạch Ngọc Lâu", input: "bachngoclau|/truyen/", script: "gen_other.js" },
        { title: "Cổ Mộng", input: "comong|https://comong.site", script: "gen_other.js" },
        { title: "Cổ Mộng Info", input: "comonginfo|https://comong.info", script: "gen_other.js" },
        { title: "Đọc Truyện", input: "doctruyen|https://doctruyen.shop", script: "gen_other.js" },
        { title: "Đọc Truyện Chill", input: "doctruyenchill|https://www.doctruyenchill.net", script: "gen_other.js" },
        { title: "Lão Phật Gia", input: "laophatgia|/", script: "gen_other.js" },
        { title: "Mê Truyện", input: "metruyen|/", script: "gen_other.js" },
        { title: "Nàng Thơ", input: "nangtho|https://nangtho.site", script: "gen_other.js" },
        { title: "Ổ Của Dưa", input: "https://doctruyen-be-ojbd.onrender.com/api/story?filter=popular&page=1&limit=20", script: "gen_ocuadua.js" },
        { title: "Ổ Truyện", input: "otruyen|/", script: "gen_other.js" },
        { title: "Say Truyện", input: "saytruyen|https://saytruyen.vn", script: "gen_other.js" },
        { title: "Tản Mộng", input: "tanmong|https://yeungontinh.site", script: "gen_other.js" },
        { title: "Tiệm Chữ Ngọt", input: "tiemchungot|https://tiemchungot.com/kham-pha", script: "gen_other.js" },
        { title: "Tiểu Hoa Đán", input: "tieuhoadan|/truyen/", script: "gen_other.js" },
        { title: "Truyện Đề Xuất", input: "truyendexuat|https://truyendexuat.com/moi-cap-nhat/", script: "gen_other.js" },
        { title: "Truyện TV", input: "truyentv|https://truyentv.site", script: "gen_other.js" },
        { title: "Vân Mộng Lâu", input: "vanmonglau|/danh-sach-truyen/", script: "gen_other.js" },
        { title: "Vivu Truyện NET", input: "/moi-cap-nhat/", script: "gen_vivutruyen_net.js" }
    ]);
}
