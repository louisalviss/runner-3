function execute(url) {
    let response = fetch(url + "&page_size=1&page_numer=1&os=android&app_version=1.0.6");

    if (response.ok) {
        let json = response.json();
        let data = json.data;
        return Response.success({
            name: data.NAME,
            cover: data.IMG,
            author: data.AUTHOR,
            description: data.DESC,
            detail: data.AUTHOR + "<br>" + data.TRANS + "<br>" + data.CAT,
            ongoing: true
        });
    }
    return null;
}