#!/usr/bin/env python3
import csv, gzip, os, sqlite3, sys
src, dst = sys.argv[1:3]
tmp = dst + '.tmp'
try:
    os.unlink(tmp)
except FileNotFoundError:
    pass
con = sqlite3.connect(tmp)
c = con.cursor()
c.execute('CREATE TABLE domains(domain TEXT PRIMARY KEY, slug TEXT UNIQUE, sitemap_part INTEGER, ordinal INTEGER, database_url TEXT, sitemap_lastmod TEXT)')
with gzip.open(src, 'rt', encoding='utf-8', newline='') as f:
    rows = ((r['domain'], r['slug'], int(r['sitemap_part']), int(r['ordinal']), r['database_url'], r['sitemap_lastmod']) for r in csv.DictReader(f))
    c.executemany('INSERT INTO domains VALUES (?,?,?,?,?,?)', rows)
c.execute('CREATE INDEX idx_domains_slug ON domains(slug)')
c.execute('CREATE INDEX idx_domains_part ON domains(sitemap_part)')
c.execute('CREATE INDEX idx_domains_ordinal ON domains(ordinal)')
con.commit()
con.close()
os.replace(tmp, dst)
print(dst)
