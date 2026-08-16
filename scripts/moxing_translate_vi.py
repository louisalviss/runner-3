#!/usr/bin/env python3
import argparse, hashlib, json, re
from pathlib import Path

MODEL_ID='Helsinki-NLP/opus-mt-zh-vi'
MODEL_REVISION='e048b2d21aebc6da81d050a4bac4e5b5178bba58'
MODEL_LICENSE='Apache-2.0'

GLOSSARY={
 '主角':'nhân vật chính','人设':'thiết lập nhân vật','爽点':'điểm sảng','爽文':'truyện sảng',
 '伏笔':'phục bút','大纲':'đại cương','节奏':'tiết tấu','世界观':'thế giới quan','升级':'thăng cấp',
 '修炼':'tu luyện','机缘':'cơ duyên','资源':'tài nguyên','读者':'độc giả','追读':'đọc tiếp',
 '开篇':'mở đầu','剧情':'tình tiết','冲突':'xung đột','高潮':'cao trào','悬念':'huyền niệm',
 '反派':'phản diện','配角':'nhân vật phụ','金手指':'kim thủ chỉ','断章':'ngắt chương',
 '网文':'webnovel','小说':'tiểu thuyết','设定':'thiết lập','铺垫':'dẫn dắt','转折':'chuyển ngoặt'
}
ZH=re.compile(r'[\u3400-\u9fff]')

def sha(s): return hashlib.sha256((s or '').encode()).hexdigest()
def glossary_terms(text): return [v for k,v in GLOSSARY.items() if k in (text or '')]
def rows(path):
    with open(path,encoding='utf-8') as f:
        for i,line in enumerate(f):
            if line.strip(): yield i,json.loads(line)

def translate(inp,out,shard,shards,batch_size,max_new_tokens):
    import torch
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    tok=AutoTokenizer.from_pretrained(MODEL_ID,revision=MODEL_REVISION)
    model=AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID,revision=MODEL_REVISION)
    model.eval(); torch.set_num_threads(max(1,min(4,torch.get_num_threads())))
    picked=[r for i,r in rows(inp) if i % shards == shard]
    target=Path(out); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8') as w:
        for start in range(0,len(picked),batch_size):
            batch=picked[start:start+batch_size]
            texts=[x['text_zh'] for x in batch]
            enc=tok(texts,return_tensors='pt',padding=True,truncation=True,max_length=480)
            with torch.inference_mode():
                gen=model.generate(**enc,max_new_tokens=max_new_tokens,num_beams=4,renormalize_logits=True,early_stopping=True)
            outs=tok.batch_decode(gen,skip_special_tokens=True)
            for x,vi in zip(batch,outs):
                vi=re.sub(r'\s+',' ',vi).strip()
                rec={
                  'source':'moxing','passage_id':x['passage_id'],'evidence_id':x['evidence_id'],
                  'text_zh_sha256':sha(x['text_zh']),'text_vi':vi,'text_vi_sha256':sha(vi),
                  'concepts_vi':glossary_terms(x['text_zh']),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,
                }
                w.write(json.dumps(rec,ensure_ascii=False)+'\n')
    manifest={'schema':'moxing-vi-translation-shard-v1','shard':shard,'shards':shards,'rows':len(picked),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,'model_license':MODEL_LICENSE}
    target.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))

def quality(path):
    total=empty=zh_heavy=0; chars=zhchars=0
    for _,r in rows(path):
        total+=1; t=r.get('text_vi','').strip(); empty+=not bool(t); c=len(t); z=len(ZH.findall(t)); chars+=c; zhchars+=z
        if c and z/c>0.25: zh_heavy+=1
    return {'rows':total,'empty':empty,'zh_heavy_rows':zh_heavy,'zh_char_ratio':round(zhchars/max(chars,1),6)}

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    t=sp.add_parser('translate');t.add_argument('--input',required=True);t.add_argument('--out',required=True);t.add_argument('--shard',type=int,required=True);t.add_argument('--shards',type=int,required=True);t.add_argument('--batch-size',type=int,default=16);t.add_argument('--max-new-tokens',type=int,default=384)
    q=sp.add_parser('quality');q.add_argument('--input',required=True)
    a=ap.parse_args()
    if a.cmd=='translate': translate(a.input,a.out,a.shard,a.shards,a.batch_size,a.max_new_tokens)
    else: print(json.dumps(quality(a.input),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
