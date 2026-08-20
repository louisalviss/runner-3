#!/usr/bin/env python3
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
BUCKET = os.environ.get('AUDIO_LIBRARY_BUCKET', 'runner3-wp-media')
STATUS = ROOT / 'ops/audio-library/chat-intake-status.json'
ITEM_PREFIX = 'audio-library/items/'
QUEUE_PREFIX = 'audio-library/queue/'

UAS = [
    'Runner3Audio/1.0 (+https://github.com/louisalviss/runner-3)',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
]


def wrangler_get(key: str):
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        run = subprocess.run(
            ['npx','-y','wrangler@4.123.0','r2','object','get',f'{BUCKET}/{key}',f'--file={path}','--remote'],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if run.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            return None
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    finally:
        path.unlink(missing_ok=True)


def wrangler_put(key: str, value: dict):
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(value, tmp, ensure_ascii=False, separators=(',', ':'))
        path = Path(tmp.name)
    try:
        subprocess.check_call([
            'npx','-y','wrangler@4.123.0','r2','object','put',f'{BUCKET}/{key}',
            f'--file={path}','--content-type=application/json; charset=utf-8','--remote'
        ], cwd=ROOT)
    finally:
        path.unlink(missing_ok=True)


def is_reddit_short(url: str) -> bool:
    p = urlparse(url)
    return (p.hostname or '').lower().endswith('reddit.com') and '/s/' in p.path


def candidates_from_html(base_url: str, text: str):
    raw = html.unescape(text or '')
    raw = raw.replace('\\u002F','/').replace('\\/','/')
    pats = [
        r'https?://(?:www\.)?reddit\.com/r/[^\s"<>]+/comments/[a-z0-9]+/[^\s"<>?]+/?',
        r'(/r/[^\s"<>]+/comments/[a-z0-9]+/[^\s"<>?]+/?)',
    ]
    out=[]
    for pat in pats:
        for m in re.finditer(pat, raw, re.I):
            value=m.group(1) if m.lastindex else m.group(0)
            value=value.rstrip('\\')
            full=urljoin(base_url, value)
            if '/comments/' in full and full not in out:
                out.append(full)
    for rel in ('canonical','og:url'):
        if rel=='canonical':
            m=re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',raw,re.I)
        else:
            m=re.search(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',raw,re.I)
        if m:
            full=urljoin(base_url, html.unescape(m.group(1)))
            if '/comments/' in full and full not in out:
                out.insert(0, full)
    return out


def resolve_requests(url: str):
    errors=[]
    for ua in UAS:
        try:
            r=requests.get(url, headers={'User-Agent':ua,'Accept':'text/html,application/xhtml+xml,*/*','Accept-Language':'en-US,en;q=0.9'}, timeout=35, allow_redirects=True)
            if '/comments/' in r.url:
                return r.url.split('?')[0], f'http:{r.status_code}'
            found=candidates_from_html(r.url, r.text)
            if found:
                return found[0].split('?')[0], f'html:{r.status_code}'
            errors.append(f'{r.status_code}/{len(r.text)}')
        except Exception as e:
            errors.append(type(e).__name__)
    return None, 'requests=' + ','.join(errors)


def resolve_browser(url: str):
    chrome = shutil.which('google-chrome') or shutil.which('chromium') or shutil.which('chromium-browser')
    if not chrome:
        return None, 'chrome-missing'
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True, executable_path=chrome, args=['--disable-dev-shm-usage','--no-sandbox'])
            ctx=browser.new_context(user_agent=UAS[1], viewport={'width':1365,'height':900}, locale='en-US')
            page=ctx.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=90000)
            except Exception:
                pass
            page.wait_for_timeout(4500)
            final=page.url
            content=page.content()
            if '/comments/' in final:
                browser.close()
                return final.split('?')[0], 'browser-url'
            try:
                canonical=page.locator('link[rel="canonical"]').get_attribute('href')
            except Exception:
                canonical=None
            if canonical and '/comments/' in canonical:
                browser.close()
                return canonical.split('?')[0], 'browser-canonical'
            found=candidates_from_html(final or url, content)
            browser.close()
            if found:
                return found[0].split('?')[0], 'browser-html'
    except Exception as e:
        return None, 'browser=' + type(e).__name__
    return None, 'browser-no-target'


def resolve(url: str):
    target, mode = resolve_requests(url)
    if target:
        return target, mode
    target2, mode2 = resolve_browser(url)
    return target2, mode + ';' + mode2


def main():
    if not STATUS.exists():
        print(json.dumps({'ok':True,'results':[],'reason':'no-status'})); return
    try:
        ids=(json.loads(STATUS.read_text(encoding='utf-8')).get('itemIds') or [])[:10]
    except Exception:
        ids=[]
    results=[]
    for item_id in ids:
        item=wrangler_get(f'{ITEM_PREFIX}{item_id}.json')
        if not item:
            results.append({'id':item_id,'status':'missing'}); continue
        src=str(item.get('sourceUrl') or '')
        if not is_reddit_short(src):
            results.append({'id':item_id,'status':'skip'}); continue
        canonical, mode=resolve(src)
        if not canonical:
            results.append({'id':item_id,'status':'unresolved','detail':mode}); continue
        now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
        item['sharedUrl']=item.get('sharedUrl') or src
        item['sourceUrl']=canonical
        item['canonicalUrl']=canonical
        item['updatedAt']=now
        item['error']=None
        wrangler_put(f'{ITEM_PREFIX}{item_id}.json', item)
        queue=wrangler_get(f'{QUEUE_PREFIX}{item_id}.json') or {'id':item_id,'createdAt':item.get('createdAt')}
        queue['sourceUrl']=canonical
        queue['sharedUrl']=src
        wrangler_put(f'{QUEUE_PREFIX}{item_id}.json', queue)
        results.append({'id':item_id,'status':'resolved','mode':mode,'canonicalResolved':True})
    print(json.dumps({'ok':True,'results':results},ensure_ascii=False))

if __name__=='__main__':
    main()
