#!/usr/bin/env python3
import argparse,json,re,sqlite3,unicodedata
from pathlib import Path

PRON_AUX=re.compile(r'^(?:ho|ong|ba|anh|chi|co|han|no|nguoi|chung|ta|toi)\s+(?:da|dang|se|la|co|khong|cung|lai|van|duoc)(?:\s|$)',re.I)
TRAIL_AUX=re.compile(r'\s+(?:da|dang|se)$',re.I)
TRIM=' .,:;!?()[]{}\"\'“”‘’|-_'

def norm(s):
    s=''.join(c for c in unicodedata.normalize('NFD',s or '') if unicodedata.category(c)!='Mn').replace('đ','d').replace('Đ','D').lower()
    return re.sub(r'\s+',' ',re.sub(r'[^0-9a-z]+',' ',s)).strip()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--index',required=True);a=ap.parse_args();root=Path(a.index);db=root/'vidian_knowledge.sqlite';con=sqlite3.connect(db)
    rows=con.execute('select id,name from entities').fetchall();delete=[];renamed=0
    for eid,name in rows:
        cleaned=(name or '').strip(TRIM);n=norm(cleaned)
        if not cleaned or PRON_AUX.search(n) or TRAIL_AUX.search(n): delete.append(eid);continue
        if cleaned!=name:
            con.execute('update entities set name=? where id=?',(cleaned,eid));renamed+=1
    if delete:
        marks=','.join('?'*len(delete))
        relids=[r[0] for r in con.execute(f'select id from relations where subject_id in ({marks}) or object_id in ({marks})',delete+delete)]
        if relids:
            rm=','.join('?'*len(relids));con.execute(f'delete from relation_evidence where relation_id in ({rm})',relids);con.execute(f'delete from relations where id in ({rm})',relids)
        con.execute(f'delete from article_entities where entity_id in ({marks})',delete);con.execute(f'delete from entities where id in ({marks})',delete)
    con.commit();con.execute('pragma optimize')
    counts={'articles':con.execute('select count(*) from articles').fetchone()[0],'entities':con.execute('select count(*) from entities').fetchone()[0],'article_entity_edges':con.execute('select count(*) from article_entities').fetchone()[0],'relations':con.execute('select count(*) from relations').fetchone()[0],'factual_relations':con.execute("select count(*) from relations where type<>'CO_OCCURS'").fetchone()[0],'fts_rows':con.execute('select count(*) from fts').fetchone()[0]};con.close()
    p=root/'manifest.json';m=json.loads(p.read_text(encoding='utf-8'));m['counts']=counts;m['cleanup']={'version':'1.1','deleted_noisy_entities':len(delete),'trimmed_entity_names':renamed,'rules':['pronoun+auxiliary fragments','trailing auxiliary fragments','terminal punctuation trim']};p.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(m['cleanup'],ensure_ascii=False));print(json.dumps(counts,ensure_ascii=False))
if __name__=='__main__':main()
