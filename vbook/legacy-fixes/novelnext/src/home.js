load('config.js');
function execute() {
    return Response.success([
        { title: "Latest Release", input: "/dayvisit/", script: "gen.js" },
        { title: "Hot Novel", input: "/allvisit/", script: "gen.js" },
        { title: "Completed Novel", input: "/full.html", script: "gen.js" },
        { title: "Most Popular", input: "/monthvisit/", script: "gen.js" },
    ]);
}
