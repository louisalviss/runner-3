load('config.js');

function execute(url) {
    let response = fetch(url);

    if (response.ok) {
        let doc = response.html();
        let el = doc.select(".list-group .list-group-item a");
        const data = [];

        if (el.size() > 0) {
            for (let i = 0; i < el.size(); i++) {
                var e = el.get(i);
                data.push({
                    name: e.select("a").text(),
                    url: "https://www.book18.org" + e.attr("href"),
                    host: "https://www.book18.org"
                });
            }
        } else {
            data.push({
                name: "0",
                url: url,
                host: "https://www.book18.org"
            });
        }

        return Response.success(data);
    }

    return null;
}