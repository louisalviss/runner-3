from __future__ import annotations

import json


def is_rate_limit(error):
    if error is None:
        return False
    if isinstance(error, dict):
        try:
            if int(error.get('code') or 0) == -2002:
                return True
        except Exception:
            pass
    text = error if isinstance(error, str) else json.dumps(error, ensure_ascii=False)
    low = text.lower()
    return 'rate limit' in low or 'limits exceeded' in low


class SemrushJobMetrics:
    def __init__(self, job):
        self.job = str(job)
        self.broker_requests = 0
        self.broker_failures = 0
        self.provider_rpc_calls = 0
        self.provider_rpc_errors = 0
        self.rate_limit_errors = 0
        self.latency_total = 0.0
        self.latency_max = 0.0
        self.by_action = {}
        self.by_method = {}

    def observe(self, request, response, elapsed_ms):
        action = str(request.get('action') or 'unknown')
        self.broker_requests += 1
        self.by_action[action] = self.by_action.get(action, 0) + 1
        elapsed_ms = max(0.0, float(elapsed_ms))
        self.latency_total += elapsed_ms
        self.latency_max = max(self.latency_max, elapsed_ms)
        if not isinstance(response, dict) or response.get('ok') is False:
            self.broker_failures += 1

        methods = []
        errors = []
        if action == 'rpc':
            methods = [str(request.get('method') or 'unknown')]
            errors = [response.get('error') if isinstance(response, dict) else 'broker failure']
        elif action == 'rpc_many':
            calls = request.get('calls') if isinstance(request.get('calls'), list) else []
            methods = [str(x.get('method') or 'unknown') for x in calls if isinstance(x, dict)]
            rows = response.get('results') if isinstance(response, dict) and isinstance(response.get('results'), list) else []
            errors = [x.get('error') if isinstance(x, dict) else 'invalid result' for x in rows]
            while len(errors) < len(methods):
                errors.append('broker failure')
        elif action == 'dpa_rpc':
            methods = [str(request.get('method') or 'unknown')]
            errors = [response.get('error') if isinstance(response, dict) else 'broker failure']

        self.provider_rpc_calls += len(methods)
        for method in methods:
            self.by_method[method] = self.by_method.get(method, 0) + 1
        for error in errors[:len(methods)]:
            if error is not None:
                self.provider_rpc_errors += 1
                if is_rate_limit(error):
                    self.rate_limit_errors += 1

    def snapshot(self):
        avg = self.latency_total / self.broker_requests if self.broker_requests else 0.0
        return {
            'job': self.job,
            'broker_requests': self.broker_requests,
            'broker_failures': self.broker_failures,
            'provider_rpc_calls': self.provider_rpc_calls,
            'provider_rpc_errors': self.provider_rpc_errors,
            'rate_limit_errors': self.rate_limit_errors,
            'broker_latency_ms_total': round(self.latency_total, 2),
            'broker_latency_ms_avg': round(avg, 2),
            'broker_latency_ms_max': round(self.latency_max, 2),
            'by_action': dict(sorted(self.by_action.items())),
            'by_method': dict(sorted(self.by_method.items())),
        }
