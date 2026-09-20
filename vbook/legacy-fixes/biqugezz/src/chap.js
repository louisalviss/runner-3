function execute(url) {
    let url2 = url.split('/').slice(0, -1).join('/')+"/";
    const doc = fetch(url).html('gbk');
    var content = doc.select(".readcontent")
    content.select(".readmiddle").remove()
    content.select(".kongwen").remove()
    content.select(".text-danger").remove()
    content = content.html();
    var nextPage = doc.select('a#linkNext').last();
    console.log(url2+nextPage.attr('href'))
    while(nextPage.text() === '下一页'){
        var doc2 = fetch(url2+nextPage.attr('href')).html('gbk');
        doc2.select(".readmiddle").remove()
        doc2.select(".kongwen").remove()
        doc2.select(".text-danger").remove()
        content += doc2.select(".readcontent").html();
        var nextPage = doc2.select('a#linkNext').last();
    }
    content = content.replace(/<p><\/p>/g,'').replace(/&nbsp;/g,'')
    return Response.success(content);
}