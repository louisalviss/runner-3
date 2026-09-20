function execute(url) {

    let storyId = /story_id=(\d+)$/.exec(url)[1];
    console.log(storyId)
    let response = fetch("http://api.mottruyen.com/listchap?story_id=" + storyId + "&os=android&app_version=1.0.6");

    if (response.ok) {

        let chapters = [];
        response.json().data.forEach(item => {
            chapters.push({
                name: item.NAME,
                url: "http://api.mottruyen.com/?chapter_id=" + item.ID
            });
        })
        return Response.success(chapters);
    }

    return null;
}



