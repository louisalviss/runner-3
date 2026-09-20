function execute() {
    return Response.success([
        { title: "玄幻小说", input: "/xuanhuan.html", script: "gen.js" },
        { title: "仙侠小说", input: "/xianxia.html", script: "gen.js" },
        { title: "都市小说", input: "/dushi.html", script: "gen.js" },
        { title: "军史小说", input: "/junshi.html", script: "gen.js" },
        { title: "网游小说", input: "/wangyou.html", script: "gen.js" },
        { title: "科幻小说", input: "/kehuan.html", script: "gen.js" },
        { title: "灵异小说", input: "/lingyi.html", script: "gen.js" },
        { title: "言情小说", input: "/yanqing.html", script: "gen.js" },
        { title: "其他小说", input: "/qita.html", script: "gen.js" }
    ]);
}
