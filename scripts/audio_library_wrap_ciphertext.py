#!/usr/bin/env python3
import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / 'ops/audio-library/chatgpt-inbox-chunks'
OUT_ROOT = ROOT / 'ops/audio-library/chatgpt-inbox-wrapped'
WIDTH = 480

results=[]
if SRC_ROOT.exists():
    for item_dir in SRC_ROOT.iterdir():
        if not item_dir.is_dir():
            continue
        manifest_path=item_dir/'manifest.json'
        if not manifest_path.exists():
            continue
        try:
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            count=int(manifest.get('chunkCount') or 0)
            cipher=''.join((item_dir/f'{i:03d}.txt').read_text(encoding='utf-8').strip() for i in range(count))
            if len(cipher) != int(manifest.get('ciphertextChars') or len(cipher)):
                raise RuntimeError('ciphertext length mismatch')
            out=OUT_ROOT/item_dir.name
            out.mkdir(parents=True,exist_ok=True)
            lines=textwrap.wrap(cipher, WIDTH)
            (out/'ciphertext.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            wrapped={
                'v':manifest.get('v',1),
                'id':manifest.get('id') or item_dir.name,
                'ephemeralPublicKey':manifest['ephemeralPublicKey'],
                'nonce':manifest['nonce'],
                'ciphertextChars':len(cipher),
                'lineWidth':WIDTH,
                'lineCount':len(lines),
            }
            (out/'manifest.json').write_text(json.dumps(wrapped,indent=2)+'\n',encoding='utf-8')
            results.append({'id':item_dir.name,'status':'wrapped','lines':len(lines),'chars':len(cipher)})
        except Exception as e:
            results.append({'id':item_dir.name,'status':'error','error':str(e)[:300]})
print(json.dumps({'ok':True,'results':results}))
