#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import socket
import time

BROKER_SOCKET = '/run/semrush-rpc-broker/control.sock'


def ts():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def journal(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'at': ts(), **event}, ensure_ascii=False, separators=(',', ':')) + '\n')


def load_bank(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    out = []
    for theme in data.get('themes', []):
        theme_id = str(theme.get('theme_id') or '').strip()
        for seed in theme.get('seeds') or []:
            seed = ' '.join(str(seed).split()).strip()
            if theme_id and seed:
                out.append((theme_id, seed))
    return data, out


def broker_call(request, timeout=180):
    payload = (json.dumps(request, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    if len(payload) > 250_000:
        raise RuntimeError('BROKER_REQUEST_TOO_LARGE')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(BROKER_SOCKET)
        sock.sendall(payload)
        reader = sock.makefile('rb')
        raw = reader.readline(8 * 1024 * 1024)
        if not raw:
            raise RuntimeError('BROKER_EMPTY_RESPONSE')
        result = json.loads(raw.decode('utf-8'))
        if not isinstance(result, dict):
            raise RuntimeError('BROKER_INVALID_RESPONSE')
        return result
    except FileNotFoundError as exc:
        raise RuntimeError('BROKER_UNAVAILABLE') from exc
    finally:
        sock.close()


def rpc_many(calls):
    response = broker_call({'action': 'rpc_many', 'calls': calls}, timeout=180)
    if response.get('ok') is not True:
        code = str(response.get('error_code') or response.get('state') or 'BROKER_RPC_FAILED')
        detail = str(response.get('detail') or '')[:600]
        raise RuntimeError(code + (':' + detail if detail else ''))
    results = response.get('results')
    if not isinstance(results, list):
        raise RuntimeError('BROKER_RPC_RESULTS_INVALID')
    return results


def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def info_args(seed, database):
    return {'phrase': seed, 'device': 0, 'currency': 'USD', 'database': database, 'date': ''}


def idea_args(seed, database, questions_only=False):
    return {
        'phrase': seed,
        'device': 0,
        'currency': 'USD',
        'database': database,
        'location': 0,
        'date': '',
        'mode': 0,
        'questions_only': bool(questions_only),
    }


def idea_rows(result):
    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return []
    for key in ('keywords', 'items', 'rows', 'data', 'results'):
        if isinstance(result.get(key), list):
            return result[key]
    return []


def load_jsonl_index(path, key_fields):
    rows = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            row = json.loads(line)
            key = tuple(row[field] for field in key_fields)
            rows[key] = row
        except Exception:
            continue
    return rows


def main():
    parser = argparse.ArgumentParser(description='Live Semrush Research collector through the single-owner NoxTools RPC broker.')
    parser.add_argument('--seed-bank', required=True)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--database', default='us')
    parser.add_argument('--max-seeds', type=int, default=0)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    bank = pathlib.Path(args.seed_bank)
    out = pathlib.Path(args.run_dir)
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / 'collection-state.json'
    journal_path = out / 'main-points.jsonl'
    preflight_path = out / 'seed-preflight.jsonl'
    ideas_path = out / 'seed-ideas.jsonl'
    universe_path = out / 'universe.json'

    bank_sha = sha(bank)
    _, seeds = load_bank(bank)
    if args.max_seeds > 0:
        seeds = seeds[:args.max_seeds]

    state = {
        'version': 2,
        'transport': 'semrush-rpc-broker-v1',
        'bank_sha256': bank_sha,
        'database': args.database,
        'stage': 'LIVE_AUTH_PENDING',
        'seed_total': len(seeds),
        'seed_done': 0,
        'server': None,
        'updated_at': ts(),
    }
    if state_path.exists() and not args.force:
        previous = json.loads(state_path.read_text(encoding='utf-8'))
        if previous.get('bank_sha256') == bank_sha and previous.get('database') == args.database:
            state = previous
            state['transport'] = 'semrush-rpc-broker-v1'
            if state.get('stage') in ('UNIVERSE_READY', 'BLOCKED_RPC_SCHEMA'):
                print(json.dumps({'status': 'RESUME_NO_BACKTRACK', 'state': state}, ensure_ascii=False))
                return 0

    atomic(state_path, state)
    journal(journal_path, {
        'event': 'RUN_START',
        'transport': 'semrush-rpc-broker-v1',
        'bank_sha256': bank_sha,
        'seed_total': len(seeds),
        'database': args.database,
    })

    try:
        ready = broker_call({'action': 'ensure'}, timeout=180)
        if ready.get('ok') is not True:
            code = str(ready.get('error_code') or ready.get('state') or 'BROKER_UNAVAILABLE')
            detail = str(ready.get('detail') or '')[:800]
            state.update(stage='BLOCKED_BROKER_BUSY' if code == 'SEMRUSH_RESOURCE_ADMISSION_DENIED' else 'BLOCKED_LIVE_AUTH_CF',
                         blocker=code, broker_detail=detail, updated_at=ts())
            atomic(state_path, state)
            journal(journal_path, {'event': 'BLOCKED', 'stage': state['stage'], 'blocker': code})
            print(json.dumps({'status': 'BLOCKED', 'reason': code, 'state': state}, ensure_ascii=False))
            return 3

        server = ready.get('server')
        state.update(stage='SEED_PREFLIGHT_RUNNING', server=server, updated_at=ts())
        for key in ('blocker', 'error', 'server_probe', 'broker_detail'):
            state.pop(key, None)
        atomic(state_path, state)
        journal(journal_path, {'event': 'LIVE_AUTH_PASS', 'transport': 'broker', 'server': server})

        done = {} if args.force else load_jsonl_index(preflight_path, ('theme_id', 'seed'))
        pending = [(theme, seed) for theme, seed in seeds if (theme, seed) not in done]
        with preflight_path.open('a', encoding='utf-8') as handle:
            for batch in chunks(pending, 4):
                calls = []
                for theme, seed in batch:
                    calls.append({'tag': 'info\t' + theme + '\t' + seed, 'method': 'keywords.GetInfo', 'args': info_args(seed, args.database)})
                    calls.append({'tag': 'summary\t' + theme + '\t' + seed, 'method': 'ideas.GetKeywordsSummary', 'args': idea_args(seed, args.database, False)})
                results = {row.get('tag'): row for row in rpc_many(calls)}
                for theme, seed in batch:
                    info = results.get('info\t' + theme + '\t' + seed, {})
                    summary = results.get('summary\t' + theme + '\t' + seed, {})
                    row = {
                        'theme_id': theme,
                        'seed': seed,
                        'info': info.get('result'),
                        'summary': summary.get('result'),
                        'errors': {'info': info.get('error'), 'summary': summary.get('error')},
                    }
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
                    done[(theme, seed)] = row
                handle.flush()
                state.update(seed_done=len(done), last_seed=batch[-1][1], updated_at=ts())
                atomic(state_path, state)
        journal(journal_path, {'event': 'SEED_PREFLIGHT_COMPLETE', 'seed_done': len(done)})

        ideas_done = {} if args.force else load_jsonl_index(ideas_path, ('theme_id', 'seed'))
        state.update(stage='UNIVERSE_EXPANDING', ideas_done=len(ideas_done), updated_at=ts())
        atomic(state_path, state)
        pending_ideas = [(theme, seed) for theme, seed in seeds if (theme, seed) not in ideas_done]
        with ideas_path.open('a', encoding='utf-8') as handle:
            for batch in chunks(pending_ideas, 4):
                calls = [
                    {'tag': 'ideas\t' + theme + '\t' + seed, 'method': 'ideas.GetKeywords', 'args': idea_args(seed, args.database, False)}
                    for theme, seed in batch
                ]
                results = {row.get('tag'): row for row in rpc_many(calls)}
                schema_error = None
                successful = []
                for theme, seed in batch:
                    result = results.get('ideas\t' + theme + '\t' + seed, {})
                    if result.get('error') is not None:
                        schema_error = {'seed': seed, 'errors': [result.get('error')]}
                        break
                    successful.append({
                        'theme_id': theme,
                        'seed': seed,
                        'ideas': idea_rows(result.get('result')),
                        'rpc_variant': 'live-ui-v1',
                    })
                for row in successful:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
                    ideas_done[(row['theme_id'], row['seed'])] = row
                handle.flush()
                state.update(ideas_done=len(ideas_done), last_seed=batch[-1][1], updated_at=ts())
                atomic(state_path, state)
                if schema_error:
                    state.update(stage='BLOCKED_RPC_SCHEMA', blocker='ideas.GetKeywords returned errors; request-shape validation required',
                                 schema_probe=schema_error, updated_at=ts())
                    atomic(state_path, state)
                    journal(journal_path, {'event': 'BLOCKED', 'stage': 'BLOCKED_RPC_SCHEMA', 'schema_probe': schema_error})
                    print(json.dumps({'status': 'BLOCKED', 'reason': 'RPC_SCHEMA', 'state': state}, ensure_ascii=False))
                    return 4

        projects = {theme: {'database': args.database, 'seeds': {}} for theme in sorted(set(theme for theme, _ in seeds))}
        for theme, seed in seeds:
            idea_row = ideas_done.get((theme, seed), {})
            projects[theme]['seeds'][seed] = {
                'summary': done.get((theme, seed), {}).get('summary'),
                'info': done.get((theme, seed), {}).get('info'),
                'ideas': idea_row.get('ideas') or [],
                'rpc_variant': idea_row.get('rpc_variant'),
            }
        atomic(universe_path, {
            'created_at': ts(),
            'source': 'Semrush Keyword RPC via NoxTools single-owner broker',
            'database': args.database,
            'seed_bank_sha256': bank_sha,
            'projects': projects,
        })
        state.update(stage='UNIVERSE_READY', universe=str(universe_path), updated_at=ts())
        atomic(state_path, state)
        journal(journal_path, {'event': 'UNIVERSE_READY', 'project_count': len(projects)})
        print(json.dumps({'status': 'PASS', 'stage': 'UNIVERSE_READY', 'projects': len(projects), 'seeds': len(seeds),
                          'universe': str(universe_path), 'transport': 'semrush-rpc-broker-v1'}, ensure_ascii=False))
        return 0
    except Exception as exc:
        state.update(stage='FAILED', error=type(exc).__name__ + ':' + str(exc)[:400], updated_at=ts())
        atomic(state_path, state)
        journal(journal_path, {'event': 'FAILED', 'error': state['error']})
        print(json.dumps({'status': 'FAIL', 'state': state}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
