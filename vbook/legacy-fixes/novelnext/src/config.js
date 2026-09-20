var BASE_URL = 'https://www.novelnext.me';
try {
    if (CONFIG_URL) {
        BASE_URL = CONFIG_URL;
    }
} catch (error) {
}

function toUrl(url) {
    if (!url) {
        return '';
    }
    if (url.indexOf('//') === 0) {
        return 'https:' + url;
    }
    if (url.indexOf('http') === 0) {
        return url.replace(/^https?:\/\/(?:www\.)?novel-next\.com/i, BASE_URL)
            .replace(/^https?:\/\/(?:www\.)?novelnext\.me/i, BASE_URL);
    }
    if (url.charAt(0) !== '/') {
        url = '/' + url;
    }
    return BASE_URL + url;
}
