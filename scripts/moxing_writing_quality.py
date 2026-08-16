#!/usr/bin/env python3
"""Quality layer for scripts/moxing_writing.py."""
import re
import moxing_writing as m

STRICT_NEG=['不要','不能','不该','不应','切忌','不宜','千万不要','尽量不要','务必不要']
STRICT_POS=['应该','应当','必须','需要','建议','最好','尽量','可以','要做到','关键是','核心是','注意','务必','不妨']
ADULT_TITLE=re.compile(r'(情色|色情|性爱|成人小说|性小说|黄文)')
ADULT_TEXT=re.compile(r'(情色小说|色情小说|性爱描写|黄文写作)')


def strict_kind(text):
    if any(x in text for x in STRICT_NEG): return 'dont',0.94
    if any(x in text for x in STRICT_POS): return 'do',0.88
    if any(x in text for x in m.TECH): return 'technique',0.72
    return 'principle',0.56


def apply():
    m.DIRECT_NEG[:] = STRICT_NEG
    m.DIRECT_POS[:] = STRICT_POS
    m.QUERY_ALIASES.update({
        'tiên hiệp':'仙侠 修炼 升级',
        'thu hút':'吸引 读者 追读',
        'nhân vật chính':'主角 人设 性格',
        'main chính':'主角 人设',
        'kỳ ngộ':'机缘 收获 奖励',
        'tài nguyên':'资源 收获 升级',
        'cao trào':'高潮 张力 节奏',
        'bí ẩn':'悬念 谜团 伏笔',
        'cliffhanger':'断章 章末 悬念',
    })
    m.kind = strict_kind
    original=m.article_parse
    def wrapped(row):
        a=original(row)
        if ADULT_TITLE.search(a.get('title','')):
            a['passages']=[]
            a['quality_excluded']='adult-writing-topic'
            return a
        a['passages']=[p for p in a.get('passages',[]) if not ADULT_TEXT.search(p.get('text',''))]
        return a
    m.article_parse=wrapped
    return m

if __name__=='__main__':
    apply(); print('moxing-writing-quality-v1.1 applied')
