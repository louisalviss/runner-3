function execute(url, page) {
    if (!page) page = '1';

    let response = fetch(url + "&page=" + page);
    if (response.ok) {
        let json = response.json();

        let novels = [];
        json.data.forEach(item => {
            novels.push({
                name: item.NAME,
                link: "http://api.mottruyen.com/story/?story_id=" + item.ID,
                cover: item.THUMB,
                description: item.AUTHOR + " - " + item.PROCESS + "(" + item.VIEWED + ")",
            });
        });
        return Response.success(novels, parseInt(page) + 1);
    }

    return null;
}