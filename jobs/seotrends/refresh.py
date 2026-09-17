#!/usr/bin/env python3
import csv, gzip, hashlib, json, os, re, shutil, sqlite3, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(os.environ.get('SEOTRENDS_PUBLIC_HOME', '/var/lib/seotrends-public'))
DATA = BASE / 'data'
CHANGES = BASE / 'changes'
DATA.mkdir(parents=True, exist_ok=True)
CHANGES.mkdir(parents=True, exist_ok=True)
UA = 'Mozilla/5.0 SeoTrendsPublicScanner/1.3'
INDEX = 'https://seotrends.pro/sitemap.xml'
NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), dict(r.headers)

def slug_to_domain(slug):
    return slug.replace('_', '.')

def read_domains(path):
    if not path.exists():
        return set()
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        return {row['domain'] for row in csv.DictReader(f)}

def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y-%m-%d')
    latest = DATA / 'domains-current.csv.gz'
    old = read_domains(latest)

    index_bytes, _ = fetch(INDEX)
    root = ET.fromstring(index_bytes)
    smaps = []
    for sm in root.findall('sm:sitemap', NS):
        loc = sm.findtext('sm:loc', default='', namespaces=NS).strip()
        lastmod = sm.findtext('sm:lastmod', default='', namespaces=NS).strip()
        if '/sitemaps/database-' in loc:
            m = re.search(r'database-(\d+)\.xml$', loc)
            if m:
                smaps.append((int(m.group(1)), loc, lastmod))
    smaps.sort()

    rows, manifest, seen, ordinal = [], [], set(), 0
    for part, url, lastmod in smaps:
        raw, hdr = fetch(url)
        sha = hashlib.sha256(raw).hexdigest()
        x = ET.fromstring(raw)
        count = 0
        for u in x.findall('sm:url', NS):
            loc = u.findtext('sm:loc', default='', namespaces=NS).strip()
            if '/database/' not in loc:
                continue
            slug = loc.rsplit('/database/', 1)[1].split('?', 1)[0].strip('/')
            if not slug or slug in seen:
                continue
            seen.add(slug)
            ordinal += 1
            count += 1
            rows.append((slug_to_domain(slug), slug, part, ordinal, loc, lastmod))
        manifest.append({'part': part, 'url': url, 'lastmod': lastmod, 'count': count, 'sha256': sha, 'etag': hdr.get('ETag', ''), 'last_modified': hdr.get('Last-Modified', '')})

    csv_path = DATA / f'domains-{stamp}.csv.gz'
    with gzip.open(csv_path, 'wt', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['domain', 'slug', 'sitemap_part', 'ordinal', 'database_url', 'sitemap_lastmod'])
        w.writerows(rows)
    shutil.copy2(csv_path, latest)

    db = DATA / 'domains.sqlite'
    tmp = DATA / 'domains.sqlite.tmp'
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    cur = con.cursor()
    cur.execute('CREATE TABLE domains(domain TEXT PRIMARY KEY, slug TEXT UNIQUE, sitemap_part INTEGER, ordinal INTEGER, database_url TEXT, sitemap_lastmod TEXT)')
    cur.executemany('INSERT INTO domains VALUES (?,?,?,?,?,?)', rows)
    cur.execute('CREATE INDEX idx_domains_slug ON domains(slug)')
    cur.execute('CREATE INDEX idx_domains_part ON domains(sitemap_part)')
    cur.execute('CREATE INDEX idx_domains_ordinal ON domains(ordinal)')
    con.commit()
    con.close()
    os.replace(tmp, db)

    new = {r[0] for r in rows}
    added = sorted(new - old) if old else []
    removed = sorted(old - new) if old else []
    (CHANGES / f'{stamp}-added.txt').write_text('\n'.join(added) + ('\n' if added else ''), encoding='utf-8')
    (CHANGES / f'{stamp}-removed.txt').write_text('\n'.join(removed) + ('\n' if removed else ''), encoding='utf-8')

    meta = {
        'generated_at': now.isoformat(), 'source_index': INDEX, 'sitemaps': manifest,
        'unique_domains': len(rows), 'added': len(added), 'removed': len(removed),
        'had_previous_state': bool(old),
        'notes': ['Public sitemap only', 'No paywalled data extracted', 'Diff uses pre-refresh domains-current snapshot']
    }
    (DATA / 'manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'domains': len(rows), 'sitemaps': len(manifest), 'added': len(added), 'removed': len(removed), 'had_previous_state': bool(old)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
