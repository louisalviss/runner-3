#!/usr/bin/env python3
"""Url-evidence SERP classifier for isolated SeoTrends Final DD review.

SHADOW-ONLY: NEVER import into the current production terminal pipeline or
promote its outputs into canonical daily verdicts without independent checks.
Keyword/title/page semantics remain unverified when the provider returns only URLs.
"""
from __future__ import annotations
import re
from collections import Counter
from urllib.parse import urlparse

SOCIAL={'youtube.com','www.youtube.com','reddit.com','www.reddit.com','facebook.com',
        'www.facebook.com','quora.com','www.quora.com','tiktok.com','www.tiktok.com'}
def norm_domain(d):
    d=(d or '').lower().strip()
    return d[4:] if d.startswith('www.') else d

INFO_SEGMENTS={'blog','blogs','guide','guides','article','articles','news','newsroom',
               'learn','learning','resource','resources','knowledge-base','glossary',
               'wiki','career-advice','posts','post','upload','courses','course',
               'slideshow','slideshows','p','stories','story','help','faq','faqs',
               'documents','document','library','publications','reviews','reference'}
ASSET_EXTS={'.pdf','.doc','.docx','.ppt','.pptx','.xls','.xlsx'}
TOOL_SEGMENT=re.compile(r'^(?:tool|tools|calculator|calculators|converter|converters|'
                        r'generator|generators|checker|checkers|lookup|validator|validators|'
                        r'editor|editors|app|apps|analyzer|analyzers)$')
TOOL_SLUG=re.compile(r'(?:^|[-_])(?:calculator|converter|generator|checker|lookup|'
                     r'validator|editor|analyzer|simulator|estimator|compressor)$')
def url_kind(url,domain=''):
    p=urlparse(str(url or '').lower()); net=norm_domain(domain or p.netloc)
    path=p.path.lower(); pieces=[part for part in path.split('/') if part]
    ext=path.rsplit('.',1)[-1] if '.' in path else ''
    if net in {norm_domain(x) for x in SOCIAL}:return 'social'
    if ('.'+ext) in ASSET_EXTS:return 'information'
    if any(piece in INFO_SEGMENTS for piece in pieces):return 'information'
    if any(TOOL_SEGMENT.fullmatch(piece) or TOOL_SLUG.search(piece) for piece in pieces):
        return 'tool'
    return 'unknown'
def classify_serp(keyword,rows):
    organic=[]; seen=set()
    for r in sorted(rows or [],key=lambda x:(999 if x.get('position') is None else x.get('position'), str(x.get('url') or ''))):
        if r.get('kind') is not None:continue
        u=str(r.get('url') or '')
        if not u or u in seen:continue
        seen.add(u); organic.append(r)
    top10=[x for x in organic if isinstance(x.get('position'),int) and x.get('position')<=10]
    if len(top10)<10:top10=organic[:10]
    kinds={'tool':[], 'information':[], 'social':[], 'unknown':[]}
    domains=[]; top=[]
    for r in top10:
        url=str(r.get('url') or '')
        d=norm_domain(str(r.get('domain') or urlparse(url).netloc))
        k=url_kind(url,d)
        kinds[k].append(d)
        domains.append(d)
        top.append({'position':r.get('position'),'domain':d,'url':url,'url_kind':k})
    counters=Counter(domains)
    feature_codes=sorted({int(f) for r in (rows or []) for f in (r.get('features') or []) if isinstance(f,int)})
    nonorganic=sum(1 for r in (rows or []) if r.get('kind') is not None)
    return {'keyword':keyword,'serp_feature_entries':nonorganic,'feature_codes':feature_codes,
            'organic_count':len(organic),'top10_domains':domains,
      'top10_unique_domains':len(set(domains)),
      'exact_tool_top10':len(kinds['tool']),'exact_tool_domains':sorted(set(kinds['tool'])),
      'article_top10':len(kinds['information']),'social_top10':len(kinds['social']),
      'unknown_top10':len(kinds['unknown']),'max_domain_repeat_top10':max(counters.values()) if counters else 0,
      'top10':top,'classification_version':3}
def gate(serps):
    if not serps:return 'BLOCKED_NO_SERP'
    if any(int(x.get('organic_count') or 0)<5 for x in serps):return 'BLOCKED_INCOMPLETE_SERP'
    avg_tool=sum(x['exact_tool_top10'] for x in serps)/len(serps)
    avg_info=sum(x['article_top10'] for x in serps)/len(serps)
    avg_unknown=sum(x['unknown_top10'] for x in serps)/len(serps)
    if len(serps)>1 and any(x['article_top10']>=6 for x in serps) and any(x['exact_tool_top10']>=5 for x in serps):
        return 'WATCH_MIXED_INTENT_SERP'
    if avg_tool>=7:return 'DROP_SERP_SATURATED'
    if avg_tool>=5:return 'WATCH_COMPETITION'
    if avg_info>=5:return 'WATCH_INFORMATIONAL_SERP'
    # URL-only evidence can't establish weak competition when most results are ambiguous.
    if avg_unknown>=4:return 'WATCH_AMBIGUOUS_SERP'
    if avg_tool<=1 and avg_info>=3:return 'WATCH_INFORMATIONAL_SERP'
    return 'SERP_DD_PASS'

