#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

BASE = pathlib.Path('/var/lib/seotrends-public')
SCANS = BASE / 'scans'
EXPORTER_PY = '/opt/chatgpt-bridge/venv/bin/python'
EXPORTER = '/opt/dhs-control/executors/semrush_dpa_export.py'
GLOBAL_BLOCKERS = ('SEM_RUSH_SM2_APIKEY_MISSING', 'SEM_RUSH_NO_USABLE_SERVER', 'GUARDIAN_DENIED', 'PROFILE_LAUNCH_TIMEOUT')


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding='utf-8'))


def existing_export_ok(path: pathlib.Path, domain: str) -> tuple[bool, dict]:
    if not path.exists() or path.stat().st_size <= 0:
        return False, {}
    try:
        data = load_json(path)
    except Exception:
        return False, {}
    ok = (
        str(data.get('domain') or '').lower() == domain.lower()
        and isinstance(data.get('rows'), list)
        and int(data.get('rows_fetched') or len(data.get('rows') or [])) >= 0
    )
    return ok, data if ok else {}


def metrics(data: dict) -> dict:
    rows = list(data.get('rows') or [])
    total_volume = 0
    traffic = 0.0
    traffic_cost = 0.0
    nonbrand_rows = 0
    domain = str(data.get('domain') or '').lower()
    brand = domain.split('.')[0].replace('-', ' ')
    top = []
    for r in rows:
        try:
            total_volume += int(float(r.get('volume') or 0))
        except Exception:
            pass
        try:
            traffic += float(r.get('traffic') or 0)
        except Exception:
            pass
        try:
            traffic_cost += float(r.get('trafficCost') or 0)
        except Exception:
            pass
        phrase = str(r.get('phrase') or '').strip()
        if phrase and brand and brand not in phrase.lower():
            nonbrand_rows += 1
        try:
            vol = int(float(r.get('volume') or 0))
        except Exception:
            vol = 0
        if phrase:
            top.append((float(r.get('trafficPercent') or 0), vol, int(r.get('position') or 999), phrase, str(r.get('url') or '')))
    top.sort(reverse=True)
    return {
        'organic_keywords': int(data.get('rows_fetched') or len(rows)),
        'reported_positions': int(data.get('total_reported') or len(rows)),
        'keyword_volume_sum_overlap_possible': total_volume,
        'estimated_traffic_sum': round(traffic, 2),
        'estimated_traffic_cost_sum': round(traffic_cost, 2),
        'nonbrand_keyword_rows': nonbrand_rows,
        'top_keywords': [
            {'keyword': x[3], 'volume': x[1], 'position': x[2], 'url': x[4]}
            for x in top[:10]
        ],
    }


def run_export(domain: str, output: pathlib.Path, timeout: int) -> dict:
    cmd = [EXPORTER_PY, EXPORTER, '--domain', domain, '--db', 'us', '--output', str(output)]
    try:
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return {'status': 'FAIL', 'domain': domain, 'reason': f'TIMEOUT:{exc.timeout}'}
    lines = [x.strip() for x in (p.stdout or '').splitlines() if x.strip()]
    parsed = None
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                parsed = obj
                break
        except Exception:
            continue
    if parsed is None:
        parsed = {
            'status': 'FAIL',
            'domain': domain,
            'reason': 'EXPORTER_UNPARSEABLE:' + ((p.stderr or p.stdout or '')[-500:]),
        }
    parsed['returncode'] = p.returncode
    return parsed


def main() -> int:
    ap = argparse.ArgumentParser(description='Consume one SeoTrends daily Semrush queue on the VPS.')
    ap.add_argument('--date', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    ap.add_argument('--queue')
    ap.add_argument('--per-domain-timeout', type=int, default=240)
    args = ap.parse_args()

    day = args.date
    queue_path = pathlib.Path(args.queue) if args.queue else SCANS / f'{day}-semrush-queue.json'
    result_path = SCANS / f'{day}-semrush-results.json'
    md_path = SCANS / f'{day}-semrush-results.md'
    out_dir = SCANS / f'{day}-semrush'
    out_dir.mkdir(parents=True, exist_ok=True)

    if not queue_path.exists():
        payload = {
            'date': day,
            'status': 'NO_QUEUE',
            'queue': str(queue_path),
            'completed_at': now_iso(),
            'items': [],
        }
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        md_path.write_text(f'# SeoTrends Semrush — {day}\n\n- status: NO_QUEUE\n', encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    queue = load_json(queue_path)
    items = list(queue.get('items') or [])
    results = []
    blocked_reason = ''

    for idx, item in enumerate(items):
        domain = str(item.get('domain') or '').strip().lower()
        if not domain:
            continue
        out = out_dir / f'{domain}.json'
        ok, data = existing_export_ok(out, domain)
        if ok:
            results.append({
                'domain': domain,
                'status': 'PASS',
                'source': 'cached-existing-export',
                'discovery_score': item.get('discovery_score'),
                'metrics': metrics(data),
                'json': str(out),
                'csv': str(out.with_suffix('.csv')),
            })
            continue

        if blocked_reason:
            results.append({
                'domain': domain,
                'status': 'NOT_RUN',
                'reason': 'GLOBAL_BLOCKER:' + blocked_reason,
                'discovery_score': item.get('discovery_score'),
            })
            continue

        exp = run_export(domain, out, args.per_domain_timeout)
        if str(exp.get('status') or '').upper() == 'PASS':
            ok2, data2 = existing_export_ok(out, domain)
            if ok2:
                results.append({
                    'domain': domain,
                    'status': 'PASS',
                    'source': 'fresh-export',
                    'discovery_score': item.get('discovery_score'),
                    'metrics': metrics(data2),
                    'json': str(out),
                    'csv': str(out.with_suffix('.csv')),
                })
            else:
                results.append({'domain': domain, 'status': 'FAIL', 'reason': 'EXPORT_FILE_INVALID'})
        else:
            reason = str(exp.get('reason') or 'UNKNOWN_EXPORT_FAILURE')
            results.append({
                'domain': domain,
                'status': 'FAIL',
                'reason': reason,
                'discovery_score': item.get('discovery_score'),
            })
            if any(marker in reason for marker in GLOBAL_BLOCKERS):
                blocked_reason = reason

    pass_count = sum(1 for r in results if r.get('status') == 'PASS')
    fail_count = sum(1 for r in results if r.get('status') == 'FAIL')
    not_run_count = sum(1 for r in results if r.get('status') == 'NOT_RUN')
    if not items:
        status = 'PASS_EMPTY'
    elif pass_count == len(items):
        status = 'PASS'
    elif blocked_reason:
        status = 'BLOCKED'
    elif pass_count:
        status = 'PARTIAL'
    else:
        status = 'FAIL'

    payload = {
        'date': day,
        'status': status,
        'source': 'seotrends-public-daily-semush-vps-consumer-v1',
        'queue': str(queue_path),
        'queue_count': len(items),
        'pass_count': pass_count,
        'fail_count': fail_count,
        'not_run_count': not_run_count,
        'global_blocker': blocked_reason or None,
        'completed_at': now_iso(),
        'items': results,
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    lines = [
        f'# SeoTrends Semrush — {day}', '',
        f'- status: {status}',
        f'- queue: {len(items)}',
        f'- PASS: {pass_count}',
        f'- FAIL: {fail_count}',
        f'- NOT_RUN: {not_run_count}',
    ]
    if blocked_reason:
        lines.append(f'- blocker: `{blocked_reason}`')
    lines += ['', '## Domains', '']
    for r in results:
        d = r.get('domain')
        st = r.get('status')
        if st == 'PASS':
            m = r.get('metrics') or {}
            lines.append(
                f'- **{d}** — PASS — organic keywords {m.get("organic_keywords", 0):,}; '
                f'traffic {m.get("estimated_traffic_sum", 0):,.2f}; '
                f'cost ${m.get("estimated_traffic_cost_sum", 0):,.2f}'
            )
        else:
            lines.append(f'- **{d}** — {st} — {r.get("reason", "-")}')
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: payload[k] for k in ('date','status','queue_count','pass_count','fail_count','not_run_count','global_blocker')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
