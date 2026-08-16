#!/usr/bin/env python3
import argparse, hashlib, json, re
from pathlib import Path

MODEL_ID='DanVP/MoxhiMT-60'
MODEL_REVISION='3ae60c790cf21deebeab8e1a82f4024fbdc1fc87'
MODEL_LICENSE='Apache-2.0'
RUNTIME='CTranslate2 INT8'

GLOSSARY={
 '主角':'nhân vật chính','人设':'thiết lập nhân vật','爽点':'điểm sảng','爽文':'truyện sảng',
 '伏笔':'phục bút','大纲':'đại cương','节奏':'tiết tấu','世界观':'thế giới quan','升级':'thăng cấp',
 '修炼':'tu luyện','机缘':'cơ duyên','资源':'tài nguyên','读者':'độc giả','追读':'đọc tiếp',
 '开篇':'mở đầu','剧情':'tình tiết','冲突':'xung đột','高潮':'cao trào','悬念':'huyền niệm',
 '反派':'phản diện','配角':'nhân vật phụ','金手指':'kim thủ chỉ','断章':'ngắt chương',
 '网文':'webnovel','小说':'tiểu thuyết','设定':'thiết lập','铺垫':'dẫn dắt','转折':'chuyển ngoặt',
 '穿越':'xuyên không','异界':'dị giới','玄幻':'huyền huyễn','三观':'tam quan','官场':'quan trường'
}
ZH=re.compile(r'[\u3400-\u9fff]')

def sha(s): return hashlib.sha256((s or '').encode()).hexdigest()
def glossary_terms(text): return [v for k,v in GLOSSARY.items() if k in (text or '')]
def rows(path):
    with open(path,encoding='utf-8') as f:
        for i,line in enumerate(f):
            if line.strip(): yield i,json.loads(line)

def _load_runtime():
    import ctranslate2
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    model_path=Path(snapshot_download(MODEL_ID,revision=MODEL_REVISION,allow_patterns=[
        'config.json','generation_config.json','source.spm','target.spm','vocab.json','tokenizer_config.json','special_tokens_map.json','ct2-int8/*'
    ]))
    tok=AutoTokenizer.from_pretrained(model_path)
    translator=ctranslate2.Translator(str(model_path/'ct2-int8'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=4)
    return tok,translator

def _translate_batch(tok,translator,texts,max_new_tokens):
    token_batches=[]
    for text in texts:
        ids=tok(text,truncation=True,max_length=512).input_ids
        token_batches.append(tok.convert_ids_to_tokens(ids))
    results=translator.translate_batch(token_batches,beam_size=4,max_decoding_length=max_new_tokens,return_scores=False)
    outs=[]
    for result in results:
        ids=tok.convert_tokens_to_ids(result.hypotheses[0])
        outs.append(tok.decode(ids,skip_special_tokens=True))
    return outs

def translate(inp,out,shard,shards,batch_size,max_new_tokens):
    tok,translator=_load_runtime()
    # Sorting by length reduces padding/decoder imbalance without changing model quality.
    picked=sorted((r for i,r in rows(inp) if i % shards == shard),key=lambda r:len(r['text_zh']))
    target=Path(out); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8') as w:
        for start in range(0,len(picked),batch_size):
            batch=picked[start:start+batch_size]
            outs=_translate_batch(tok,translator,[x['text_zh'] for x in batch],max_new_tokens)
            for x,vi in zip(batch,outs):
                vi=re.sub(r'\s+',' ',vi).strip()
                rec={
                  'source':'moxing','passage_id':x['passage_id'],'evidence_id':x['evidence_id'],
                  'text_zh_sha256':sha(x['text_zh']),'text_vi':vi,'text_vi_sha256':sha(vi),
                  'concepts_vi':glossary_terms(x['text_zh']),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,
                  'model_license':MODEL_LICENSE,'runtime':RUNTIME,
                }
                w.write(json.dumps(rec,ensure_ascii=False)+'\n')
            if start % max(batch_size*10,batch_size)==0:
                print(json.dumps({'shard':shard,'done':min(start+len(batch),len(picked)),'total':len(picked)},ensure_ascii=False),flush=True)
    manifest={'schema':'moxing-vi-translation-shard-v1.1','shard':shard,'shards':shards,'rows':len(picked),'model_id':MODEL_ID,'model_revision':MODEL_REVISION,'model_license':MODEL_LICENSE,'runtime':RUNTIME}
    target.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))

def quality(path):
    total=empty=zh_heavy=length_outlier=0; chars=zhchars=0
    for _,r in rows(path):
        total+=1; t=r.get('text_vi','').strip(); empty+=not bool(t); c=len(t); z=len(ZH.findall(t)); chars+=c; zhchars+=z
        if c and z/c>0.25: zh_heavy+=1
        if c>900: length_outlier+=1
    return {'rows':total,'empty':empty,'zh_heavy_rows':zh_heavy,'zh_char_ratio':round(zhchars/max(chars,1),6),'length_outlier_rows':length_outlier}

def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True)
    t=sp.add_parser('translate');t.add_argument('--input',required=True);t.add_argument('--out',required=True);t.add_argument('--shard',type=int,required=True);t.add_argument('--shards',type=int,required=True);t.add_argument('--batch-size',type=int,default=24);t.add_argument('--max-new-tokens',type=int,default=512)
    q=sp.add_parser('quality');q.add_argument('--input',required=True)
    a=ap.parse_args()
    if a.cmd=='translate': translate(a.input,a.out,a.shard,a.shards,a.batch_size,a.max_new_tokens)
    else: print(json.dumps(quality(a.input),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
