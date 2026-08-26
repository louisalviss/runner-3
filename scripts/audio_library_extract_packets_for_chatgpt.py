#!/usr/bin/env python3
# trigger: packetize-v3-core-scoped
import importlib.util
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import audio_media_core as media

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ITEM_PREFIX = 'audio-library/items/'
STATUS = ROOT / 'ops/audio-library/chatgpt-inbox-status.json'
OUT_ROOT = ROOT / 'ops/audio-library/chatgpt-inbox-records'
PACKET_CHARS = int(os.environ.get('AUDIO_LIBRARY_PACKET_CHARS', '3500'))


def load_core():
    path = SCRIPT_DIR / 'audio_library_extract_for_chatgpt.py'
    spec = importlib.util.spec_from_file_location('_runner3_audio_packet_core', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('unable to load audio extractor core')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ('extract_source', 'clean_text', 'trim_raw', 'encrypt_payload'):
        if not callable(getattr(module, name, None)):
            raise RuntimeError(f'audio extractor {name} missing from {path}')
    return module


core = load_core()


def ids_from_status():
    ids=[]
    try:
        data=json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
    except Exception:
        data={}
    def add(v):
        v=str(v or '')
        if v and v not in ids:
            ids.append(v)
    for section in ('resolver','fxheaders','metadata','fallback','extractor'):
        for row in ((data.get(section) or {}).get('results') or []):
            if isinstance(row,dict): add(row.get('id'))
    return ids[:10]


def split_packets(text: str):
    paras=[p.strip() for p in text.split('\n\n') if p.strip()]
    out=[]; cur=''
    for p in paras:
        if len(p) > PACKET_CHARS:
            if cur:
                out.append(cur); cur=''
            for i in range(0,len(p),PACKET_CHARS):
                out.append(p[i:i+PACKET_CHARS])
            continue
        candidate = p if not cur else cur+'\n\n'+p
        if len(candidate) <= PACKET_CHARS:
            cur=candidate
        else:
            if cur: out.append(cur)
            cur=p
    if cur: out.append(cur)
    return out


def main():
    recipient=os.environ.get('CHATGPT_INBOX_PUBLIC_KEY','').strip()
    if not recipient:
        raise SystemExit('CHATGPT_INBOX_PUBLIC_KEY missing')
    results=[]
    for item_id in ids_from_status():
        try:
            item=media.get_json(f'{ITEM_PREFIX}{item_id}.json')
        except Exception as error:
            results.append({'id':item_id,'status':'error','error':f'core_read:{type(error).__name__}'})
            continue
        if not item or item.get('audioUrl'):
            continue
        source_url=str(item.get('sourceUrl') or '')
        if not source_url:
            continue
        target=OUT_ROOT/item_id
        manifest=target/'manifest.json'
        if manifest.exists():
            results.append({'id':item_id,'status':'skip_existing'})
            continue
        try:
            with tempfile.TemporaryDirectory(prefix='audio-packets-') as td:
                title, raw, source_label, canonical = core.extract_source(source_url, Path(td))
            raw=core.clean_text(raw)
            raw,_=core.trim_raw(raw)
            packets=split_packets(raw)
            if not packets:
                raise RuntimeError('no packets')
            target.mkdir(parents=True,exist_ok=True)
            count=len(packets)
            for idx,text in enumerate(packets):
                payload={
                    'id':item_id,
                    'packetIndex':idx,
                    'packetCount':count,
                    'title':title,
                    'sourceLabel':source_label,
                    'canonicalUrl':canonical,
                    'text':text,
                    'extractedAt':datetime.now(timezone.utc).isoformat(),
                    'editorPolicy':'RAW_SOURCE_ONLY_NO_TRANSLATION_NO_SUMMARY_NO_LLM',
                }
                env=core.encrypt_payload(payload, recipient)
                (target/f'{idx:03d}.json').write_text(json.dumps(env,separators=(',',':'))+'\n',encoding='utf-8')
            manifest.write_text(json.dumps({'v':1,'id':item_id,'packetCount':count,'packetChars':PACKET_CHARS},indent=2)+'\n',encoding='utf-8')
            results.append({'id':item_id,'status':'packetized','packets':count,'chars':len(raw)})
        except Exception as e:
            results.append({'id':item_id,'status':'error','error':str(e)[:500]})
    print(json.dumps({'ok':True,'results':results},ensure_ascii=False))


if __name__=='__main__':
    main()
