function thBrowserGet(url){
    var browser=null;
    try{
        browser=Engine.newBrowser();
        browser.launchAsync(url);
        sleep(5000);
        var h=String(browser.html()||'');
        try{browser.close();}catch(e0){}
        return h;
    }catch(e){
        try{if(browser)browser.close();}catch(e1){}
        return '';
    }
}
