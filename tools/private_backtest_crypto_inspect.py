#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, tarfile, tempfile
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT='private-backtest'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--scope',required=True); a=ap.parse_args()
    work=Path(tempfile.mkdtemp(prefix='crypto-inspect-'))
    for sid in (0,1):
        ar=work/f'shard-{sid:02d}.tar.gz'
        core.download_artifact(PROJECT,a.scope,f'shards/shard-{sid:02d}.tar.gz',ar)
        dst=work/f'x{sid}'; dst.mkdir()
        with tarfile.open(ar,'r:gz') as tf: tf.extractall(dst)
        for p in sorted(dst.glob('symbols/*/summary-*.json')):
            try:
                d=json.loads(p.read_text(encoding='utf-8'))
                print(json.dumps({'file':str(p.relative_to(dst)),'summary':d},ensure_ascii=False))
            except Exception as e: print(json.dumps({'file':str(p),'error':repr(e)}))
        for p in sorted(dst.glob('symbols/*/runner-error.json')):
            d=json.loads(p.read_text(encoding='utf-8'))
            print(json.dumps({'file':str(p.relative_to(dst)),'runner_error':d},ensure_ascii=False))
if __name__=='__main__': main()
