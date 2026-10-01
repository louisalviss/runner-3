import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def load_bt():
    p = Path(__file__).with_name('wr_crossasset_backtest.py')
    spec = importlib.util.spec_from_file_location('wr_crossasset_backtest_cache_source', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    m = load_bt()
    symbol = a.symbol.upper()
    if symbol not in m.ASSETS:
        raise SystemExit(f'unknown symbol {symbol}')

    # Dukascopy still exposes Meta Platforms history under the legacy FB ticker.
    original_resolve = m.resolve_symbol
    if symbol == 'META':
        m.resolve_symbol = lambda s: 'FB.US/USD' if s.upper() == 'META' else original_resolve(s)

    df, month_manifest, instrument = m.download_m5(symbol)
    if not len(df):
        raise RuntimeError(f'{symbol}: empty dataset')
    if not df.index.is_monotonic_increasing:
        raise RuntimeError(f'{symbol}: timestamps not sorted')
    if df.index.has_duplicates:
        raise RuntimeError(f'{symbol}: duplicate timestamps')

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = df[['open', 'high', 'low', 'close']].copy()
    df.index.name = 'timestamp_utc'

    parquet = out / f'{symbol}_M5_DUKASCOPY_20211201_20260821.parquet'
    df.to_parquet(parquet, engine='pyarrow', compression='zstd', index=True)

    first = df.index[0].isoformat()
    last = df.index[-1].isoformat()
    entry = {
        'schema_version': 1,
        'symbol': symbol,
        'group': m.ASSETS[symbol]['group'],
        'source': 'Dukascopy public historical data',
        'offer_side': 'BID',
        'source_instrument': instrument,
        'timeframe': '5m',
        'timezone': 'UTC',
        'warmup_start_requested': m.STATE_START.isoformat(),
        'end_exclusive_requested': m.END.isoformat(),
        'first_timestamp_utc': first,
        'last_timestamp_utc': last,
        'rows': int(len(df)),
        'columns': ['timestamp_utc', 'open', 'high', 'low', 'close'],
        'dtypes': {c: str(df[c].dtype) for c in df.columns},
        'file': parquet.name,
        'bytes': parquet.stat().st_size,
        'sha256': sha256(parquet),
        'month_manifest': month_manifest,
        'notes': [
            'Raw canonical cache for strategy research; no Wave Rider filters or labels are embedded.',
            'Build 10m only from exactly two contiguous 5m children at t and t+5m; reject incomplete buckets.',
            'US500/NAS100 are Dukascopy index CFDs; US equities are Dukascopy stock CFDs, not exchange prints.',
            'META maps to Dukascopy legacy FB.US/USD history.' if symbol == 'META' else ''
        ]
    }
    entry['notes'] = [x for x in entry['notes'] if x]
    with open(out / f'manifest_entry_{symbol}.json', 'w') as f:
        json.dump(entry, f, indent=2)
    print(json.dumps({k: entry[k] for k in ('symbol','group','source_instrument','rows','first_timestamp_utc','last_timestamp_utc','bytes','sha256')}))


if __name__ == '__main__':
    main()
