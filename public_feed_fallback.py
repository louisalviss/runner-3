#!/usr/bin/env python3
import argparse, email.utils, html, json, re, urllib.request
from datetime import timezone
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

UA = 'Mozilla/5.0 (compatible; Runner3PublicFeed/1.0)'


def clean_markup(value):
    s = html.unescape(str(value or ''))
    s = re.sub(r'<(script|style)[^>]*>.*?</\\1>', ' ', s, flags=re.I|re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\\s+', ' ', s).strip()


def iso_date(value):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.7'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.status, r.read(2_500_000)


def parse_feed(data, source, feed_url, limit=30):
    root = ET.fromstring(data)
    rows = []
    items = list(root.findall('.//item'))
    if not items:
        atom = {'a': 'http://www.w3.org/2005/Atom'}
        for e in root.findall('.//a:entry', atom):
            title = ''.join(e.findtext('a:title', default='', namespaces=atom) or '')
            link = ''
            le = e.find('a:link', atom)
            if le is not None:
                link = le.attrib.get('href', '')
            text = clean_markup(e.findtext('a:content', default='', namespaces=atom) or e.findtext('a:summary', default='', namespaces=atom) or '')
            rows.append({'source': source, 'thread_title': clean_markup(title), 'thread_url': link, 'fetched_url': link, 'timestamp': e.findtext('a:updated', default='', namespaces=atom), 'text': text})
    else:
        for e in items:
            title = clean_markup(e.findtext('title') or '')
            link = (e.findtext('link') or '').strip()
            pub = e.findtext('pubDate') or e.findtext('{http://purl.org/dc/elements/1.1/}date') or ''
            desc = e.findtext('description') or ''
            content = e.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or ''
            text = clean_markup(content or desc)
            if not text:
                text = title
            rows.append({'source': source, 'thread_title': title, 'thread_url': link, 'fetched_url': link, 'timestamp': iso_date(pub), 'text': text})
    out=[]
    for i, row in enumerate(rows[:limit]):
        row.update({
            'thread_key': (urlparse(row.get('thread_url') or '').hostname or '') + (urlparse(row.get('thread_url') or '').path or ''),
            'fetched_at': __import__('datetime').datetime.now(timezone.utc).isoformat(),
            'pre_score': 1.0,
            'pre_score_details': {'fallback': 'public_feed', 'feed_url': feed_url, 'feed_order': i},
            'post_id': '', 'author': '', 'text_chars': len(row.get('text') or ''), 'extraction': 'feed_fallback',
        })
        out.append(row)
    return out


def feeds_from_job(job):
    feeds=[]
    for src in job.get('sources') or []:
        name=str(src.get('name') or '')
        for u in src.get('discovery_urls') or []:
            p=urlparse(u)
            if (p.hostname or '').lower() == 'voz.vn' and p.path.startswith('/f/'):
                rss=u.rstrip('/') + '/index.rss'
                feeds.append((name, rss))
                break
    return feeds


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--job', default='forum-jobs/forum-signal-vn.json')
    ap.add_argument('--manifest', default='crawl_output/manifest.json')
    ap.add_argument('--output', default='crawl_output/forum_signal.jsonl')
    ap.add_argument('--summary', default='crawl_output/public_feed_fallback.json')
    ap.add_argument('--force-all', action='store_true')
    args=ap.parse_args()
    job=json.loads(Path(args.job).read_text(encoding='utf-8'))
    manifest={}
    mp=Path(args.manifest)
    if mp.exists():
        manifest=json.loads(mp.read_text(encoding='utf-8'))
    health={x.get('source'):x for x in (manifest.get('sources') or [])}
    selected=[]
    for name,url in feeds_from_job(job):
        h=health.get(name,{})
        if args.force_all or not h or int(h.get('threads_ok') or 0) == 0:
            selected.append((name,url))
    existing=set()
    outp=Path(args.output)
    if outp.exists():
        for line in outp.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line); existing.add((r.get('source'),r.get('thread_url')))
            except Exception: pass
    added=[]; report=[]
    for name,url in selected:
        try:
            final,status,data=fetch(url)
            rows=parse_feed(data,name,final)
            fresh=[r for r in rows if (r.get('source'),r.get('thread_url')) not in existing]
            added.extend(fresh)
            report.append({'source':name,'feed':url,'status':status,'items':len(rows),'added':len(fresh),'ok':True})
        except Exception as e:
            report.append({'source':name,'feed':url,'ok':False,'error':f'{type(e).__name__}: {e}'})
    if added:
        outp.parent.mkdir(parents=True,exist_ok=True)
        with outp.open('a',encoding='utf-8') as f:
            for r in added:
                f.write(json.dumps(r,ensure_ascii=False) + chr(10))
    summary={'selected_feeds':len(selected),'rows_added':len(added),'feeds':report,'coverage_note':'RSS fallback is discovery/first-post text only; it does not claim full thread-comment coverage.'}
    Path(args.summary).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__ == '__main__': main()
