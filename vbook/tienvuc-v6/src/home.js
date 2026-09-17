function execute() {
    return Response.success([
        { title: "Cập nhật", input: "new-books", script: "gen.js" },
        { title: "Miễn phí", input: "hot-free-books", script: "gen.js" },
        { title: "Truyện VIP", input: "hot-books", script: "gen.js" },
        { title: "Hoàn thành", input: "full-books", script: "gen.js" }
    ]);
}
