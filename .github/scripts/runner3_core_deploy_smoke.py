#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

DEPLOY_LOG = pathlib.Path('/tmp/runner3-core-deploy.log')
SMOKE_RESULT = pathlib.Path('/tmp/runner3-core-smoke.json')
KNOWN_URL = 'https://runner3-core.ducduy2411.workers.dev'
BROWSER_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'


def core_url():
    log = DEPLOY_LOG.read_text(errors='replace') if DEPLOY_LOG.exists() else ''
    urls = re.findall(r'https://[A-Za-z0-9.-]+\.workers\.dev', log)
    base = next((u.rstrip('/') for u in urls if 'runner3-core.' in u), None)
    return base or KNOWN_URL, bool(base)


def request_json(base, token, path, method='GET', payload=None, authenticated=True):
    data = json.dumps(payload, separators=(',', ':')).encode() if payload is not None else None
    headers = {
        'Accept': 'application/json',
        'User-Agent': BROWSER_UA,
        'Cache-Control': 'no-cache',
    }
    if authenticated:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode(errors='replace')
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = None
            return {'http': response.status, 'json': parsed, 'body': raw[:1000]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors='replace')
        try:
            parsed = json.loads(raw) if raw else None
        except Exception:
            parsed = None
        return {'http': exc.code, 'json': parsed, 'body': raw[:1000], 'error': str(exc)}
    except Exception as exc:
        return {'http': 0, 'json': None, 'body': '', 'error': str(exc)[:1000]}


def request_bytes(url, method='GET'):
    req = urllib.request.Request(url, headers={'User-Agent': BROWSER_UA, 'Cache-Control': 'no-cache'}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return {
                'http': response.status,
                'bytes': raw,
                'content_type': response.headers.get('Content-Type'),
                'content_disposition': response.headers.get('Content-Disposition'),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {'http': exc.code, 'bytes': raw, 'error': str(exc)}
    except Exception as exc:
        return {'http': 0, 'bytes': b'', 'error': str(exc)[:1000]}


def wait_for_required_auth(base, token, run_id, attempts=20):
    path = '/checkpoints/runner3-core-auth-proof/unauth-' + urllib.parse.quote(run_id, safe='')
    payload = {
        'source': 'runner3-core-auth-proof',
        'status': 'failed-if-written',
        'position': {'probe': 'unauthenticated'},
    }
    observed = []
    consecutive = 0
    health = None
    for _ in range(attempts):
        health = request_json(base, token, '/health', authenticated=False)
        health_json = health.get('json') if isinstance(health.get('json'), dict) else {}
        probe = request_json(base, token, path, 'PUT', payload, authenticated=False)
        status = probe.get('http')
        observed.append(status)
        if health.get('http') == 200 and health_json.get('write_auth') == 'required' and status == 401:
            consecutive += 1
            if consecutive >= 3:
                return health, probe, observed
        else:
            consecutive = 0
        time.sleep(1)
    return health, probe, observed


def main():
    base, from_deploy_log = core_url()
    token = os.environ.get('RUNNER3_CORE_TOKEN', '').strip()
    if not token:
        raise SystemExit('RUNNER3_CORE_TOKEN secret missing')

    checked = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
    run_id = os.environ.get('GITHUB_RUN_ID', 'manual')
    health, unauth_checkpoint, unauth_observed = wait_for_required_auth(base, token, run_id)
    health_json = health.get('json') if isinstance(health.get('json'), dict) else {}

    posted = request_json(base, token, '/events', 'POST', {
        'source': 'runner3-core-shadow',
        'event_type': 'health',
        'payload': {'status': 'ok', 'checkedAt': checked},
    })
    latest = request_json(base, token, '/events/latest', authenticated=False)
    status = request_json(base, token, '/status', authenticated=False)

    state_source = 'runner3-core-smoke'
    state_path = '/state/' + urllib.parse.quote(state_source, safe='')
    state_payload = {
        'status': 'success',
        'run_id': run_id,
        'detail': {'kind': 'deploy-smoke', 'checkedAt': checked, 'auth': 'bearer'},
    }
    state_put = request_json(base, token, state_path, 'PUT', state_payload)
    state_get = request_json(base, token, state_path, authenticated=False)

    checkpoint_project = 'runner3-core-smoke'
    checkpoint_scope = 'deploy'
    checkpoint_path = '/checkpoints/' + urllib.parse.quote(checkpoint_project, safe='') + '/' + urllib.parse.quote(checkpoint_scope, safe='')
    checkpoint_payload = {
        'source': 'runner3-core-smoke',
        'status': 'success',
        'position': {'phase': 'deployed', 'run_id': run_id, 'auth': 'bearer'},
        'dropbox_path': None,
        'last_error': None,
    }
    checkpoint_put = request_json(base, token, checkpoint_path, 'PUT', checkpoint_payload)
    checkpoint_get = request_json(base, token, checkpoint_path, authenticated=False)

    artifact_project = 'runner3-core-smoke'
    artifact_scope = run_id
    artifact_name = 'proof.json'
    artifact_path = '/artifacts/' + urllib.parse.quote(artifact_project, safe='') + '/' + urllib.parse.quote(artifact_scope, safe='') + '/' + artifact_name
    artifact_payload = {'kind': 'runner3-core-auth-proof', 'run_id': run_id, 'checkedAt': checked}
    artifact_raw = json.dumps(artifact_payload, separators=(',', ':')).encode()
    artifact_unauth = request_json(base, token, artifact_path, 'HEAD', authenticated=False)
    artifact_put = request_json(base, token, artifact_path, 'PUT', artifact_payload)
    artifact_get = request_json(base, token, artifact_path, 'GET')

    delivery_unauth_create = request_json(base, token, '/delivery-links', 'POST', {
        'project': artifact_project, 'scope': artifact_scope, 'name': artifact_name, 'ttl_seconds': 120,
    }, authenticated=False)
    delivery_create = request_json(base, token, '/delivery-links', 'POST', {
        'project': artifact_project, 'scope': artifact_scope, 'name': artifact_name, 'ttl_seconds': 120,
    })
    delivery_json = delivery_create.get('json') if isinstance(delivery_create.get('json'), dict) else {}
    delivery_record = delivery_json.get('delivery') if isinstance(delivery_json.get('delivery'), dict) else {}
    signed_url = str(delivery_record.get('url') or '')
    delivery_get = request_bytes(signed_url) if signed_url.startswith(base + '/delivery/') else {'http': 0, 'bytes': b'', 'error': 'signed-url-invalid'}
    unsigned_path = '/delivery/' + '/'.join(urllib.parse.quote(x, safe='') for x in [artifact_project, artifact_scope, artifact_name])
    delivery_unsigned = request_json(base, token, unsigned_path, authenticated=False)
    tampered_url = ''
    if signed_url:
        parsed = urllib.parse.urlsplit(signed_url)
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        sig = (params.get('sig') or [''])[0]
        if sig:
            params['sig'] = [('A' if sig[0] != 'A' else 'B') + sig[1:]]
        tampered_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(params, doseq=True), parsed.fragment))
    delivery_tampered = request_bytes(tampered_url) if tampered_url else {'http': 0, 'bytes': b'', 'error': 'no-tampered-url'}

    latest_json = latest.get('json')
    status_json = status.get('json') if isinstance(status.get('json'), dict) else {}
    state_get_json = state_get.get('json') if isinstance(state_get.get('json'), dict) else {}
    state_record = state_get_json.get('state') if isinstance(state_get_json.get('state'), dict) else {}
    checkpoint_get_json = checkpoint_get.get('json') if isinstance(checkpoint_get.get('json'), dict) else {}
    checkpoint_record = checkpoint_get_json.get('checkpoint') if isinstance(checkpoint_get_json.get('checkpoint'), dict) else {}
    artifact_get_json = artifact_get.get('json') if isinstance(artifact_get.get('json'), dict) else {}

    auth_ok = bool(
        health.get('http') == 200
        and health_json.get('write_auth') == 'required'
        and health_json.get('artifact_auth') is True
        and len(unauth_observed) >= 3
        and unauth_observed[-3:] == [401, 401, 401]
    )
    state_ok = bool(
        state_put.get('http') == 200
        and state_get.get('http') == 200
        and state_get_json.get('ok') is True
        and state_record.get('source') == state_source
        and state_record.get('status') == 'success'
        and str(state_record.get('run_id')) == run_id
        and isinstance(state_record.get('detail'), dict)
        and state_record['detail'].get('auth') == 'bearer'
    )
    checkpoint_ok = bool(
        checkpoint_put.get('http') == 200
        and checkpoint_get.get('http') == 200
        and checkpoint_get_json.get('ok') is True
        and checkpoint_record.get('project') == checkpoint_project
        and checkpoint_record.get('scope') == checkpoint_scope
        and checkpoint_record.get('status') == 'success'
        and isinstance(checkpoint_record.get('position'), dict)
        and checkpoint_record['position'].get('auth') == 'bearer'
        and str(checkpoint_record['position'].get('run_id')) == run_id
    )
    artifact_ok = bool(
        artifact_unauth.get('http') == 401
        and artifact_put.get('http') == 200
        and artifact_get.get('http') == 200
        and artifact_get_json == artifact_payload
    )
    delivery_ok = bool(
        delivery_unauth_create.get('http') == 401
        and delivery_create.get('http') == 200
        and delivery_json.get('ok') is True
        and signed_url.startswith(base + '/delivery/')
        and delivery_get.get('http') == 200
        and delivery_get.get('bytes') == artifact_raw
        and delivery_unsigned.get('http') == 401
        and delivery_tampered.get('http') == 401
        and 'attachment' in str(delivery_get.get('content_disposition') or '').lower()
    )
    status_ok = bool(status.get('http') == 200 and status_json.get('ok') is True and isinstance(status_json.get('sources'), dict))
    post_ok = bool(posted.get('http') == 200 and isinstance(posted.get('json'), dict) and posted['json'].get('ok') is True)
    latest_ok = bool(latest.get('http') == 200 and isinstance(latest_json, list) and len(latest_json) >= 1)

    result = {
        'checkedAt': checked,
        'url': base,
        'd1DatabaseId': pathlib.Path('/tmp/d1-id').read_text().strip() if pathlib.Path('/tmp/d1-id').exists() else None,
        'deployUrlSource': 'wrangler-output' if from_deploy_log else 'known-fallback',
        'health': health,
        'auth': {
            'ok': auth_ok,
            'unauthenticatedCheckpointWriteHttp': unauth_checkpoint.get('http'),
            'unauthenticatedCheckpointObserved': unauth_observed,
            'unauthenticatedArtifactHeadHttp': artifact_unauth.get('http'),
        },
        'postEvent': posted,
        'latest': {**latest, 'count': len(latest_json) if isinstance(latest_json, list) else None},
        'status': {**status, 'schemaOk': status_ok},
        'state': {'put': state_put, 'get': state_get, 'ok': state_ok},
        'checkpoint': {'put': checkpoint_put, 'get': checkpoint_get, 'ok': checkpoint_ok},
        'artifact': {'put': artifact_put, 'get': artifact_get, 'ok': artifact_ok},
        'delivery': {
            'ok': delivery_ok,
            'unauthenticatedCreateHttp': delivery_unauth_create.get('http'),
            'createHttp': delivery_create.get('http'),
            'unsignedGetHttp': delivery_unsigned.get('http'),
            'tamperedGetHttp': delivery_tampered.get('http'),
            'signedGetHttp': delivery_get.get('http'),
            'signedBytes': len(delivery_get.get('bytes') or b''),
            'signedSha256': hashlib.sha256(delivery_get.get('bytes') or b'').hexdigest(),
            'expectedSha256': hashlib.sha256(artifact_raw).hexdigest(),
            'contentDisposition': delivery_get.get('content_disposition'),
            'ttlSeconds': delivery_record.get('ttl_seconds'),
        },
        'ok': bool(
            health_json.get('ok') is True
            and health_json.get('d1') is True
            and health_json.get('r2') is True
            and auth_ok and post_ok and latest_ok and status_ok and state_ok and checkpoint_ok and artifact_ok and delivery_ok
        ),
    }

    SMOKE_RESULT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['ok']:
        raise SystemExit('runner3_core_smoke_failed')


if __name__ == '__main__':
    main()
