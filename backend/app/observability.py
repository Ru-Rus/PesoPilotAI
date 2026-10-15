"""Bounded, payload-free request metrics, W3C trace IDs and error alerts."""
import secrets
import threading
import time
from collections import Counter, deque
from uuid import uuid4
from typing import TypedDict

class Trace(TypedDict):
    trace_id: str
    span_id: str
    request_id: str
    method: str
    route: str
    status: int
    duration_ms: float

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from .db import settings

router = APIRouter()
lock = threading.Lock()
counts: Counter[tuple[str, str, int]] = Counter()
latencies: Counter[float | str] = Counter()
traces: deque[Trace] = deque(maxlen=500)
started = time.monotonic()
BUCKETS = (0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10)


def observe(method, route, status, elapsed, request_id):
    method = method if method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS') else 'OTHER'
    trace_id, span_id = uuid4().hex, uuid4().hex[:16]
    with lock:
        counts[(method, route, status)] += 1
        for boundary in BUCKETS:
            if elapsed <= boundary:
                latencies[boundary] += 1
        latencies['count'] += 1
        latencies['sum'] += elapsed
        traces.append({'trace_id': trace_id, 'span_id': span_id, 'request_id': request_id, 'method': method,
            'route': route, 'status': status, 'duration_ms': round(elapsed * 1000, 3)})
    return f'00-{trace_id}-{span_id}-01'


def operator(request):
    if not settings.metrics_token:
        raise HTTPException(503, 'Operator telemetry credential is not configured')
    supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not secrets.compare_digest(supplied, settings.metrics_token):
        raise HTTPException(403, 'Operator authorization required')


@router.get('/metrics')
def metrics(request: Request):
    operator(request)
    with lock:
        lines = ['# TYPE pesopilot_requests_total counter']
        for (method, route, status), count in sorted(counts.items()):
            lines.append(f'pesopilot_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}')
        lines.append('# TYPE pesopilot_request_duration_seconds histogram')
        for boundary in BUCKETS:
            lines.append(f'pesopilot_request_duration_seconds_bucket{{le="{boundary}"}} {latencies[boundary]}')
        lines += [f'pesopilot_request_duration_seconds_bucket{{le="+Inf"}} {latencies["count"]}',
            f'pesopilot_request_duration_seconds_count {latencies["count"]}', f'pesopilot_request_duration_seconds_sum {latencies["sum"]}',
            f'pesopilot_uptime_seconds {time.monotonic() - started}']
    return Response('\n'.join(lines) + '\n', media_type='text/plain')


@router.get('/traces')
def recent_traces(request: Request):
    operator(request)
    with lock:
        return list(traces)


@router.get('/alerts')
def alerts(request: Request):
    operator(request)
    with lock:
        failures = sum(trace['status'] >= 500 for trace in traces)
        total = len(traces)
    return {'recent_requests': total, 'server_errors': failures, 'error_rate_alert': total >= 20 and failures * 20 >= total,
        'scope': 'Bounded process-local sample. Configure external scraping and notification before production.'}
