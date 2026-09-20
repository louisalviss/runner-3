function execute() {
    var response = fetch("http://api.mottruyen.com/getListCategory");
    if (response.ok) {
        let json = response.json();

        let genre = [];
        json.data.forEach(item => {
            genre.push({
                title: item.NAME,
                input: "http://api.mottruyen.com/filter?status=0&totalchapter=0&cat=" + item.ID + "&date=0&kind=0&sort=0&os=android&app_version=1.0.6",
                script: "gen.js"
            });
        })

        return Response.success(genre);
    }

    return null;
}
