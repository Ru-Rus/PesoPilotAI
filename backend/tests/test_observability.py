import re
from app.db import settings


def test_operator_metrics_and_trace_privacy(client, monkeypatch):
    c, _ = client
    assert c.get('/internal/metrics').status_code == 503
    monkeypatch.setattr(settings, 'metrics_token', 'synthetic-operator-token')
    assert c.get('/internal/metrics').status_code == 403
    response = c.get('/health/live?private=PRIVATE_FINANCIAL_VALUE')
    assert re.fullmatch(r'00-[0-9a-f]{32}-[0-9a-f]{16}-01', response.headers['traceparent'])
    headers = {'Authorization': 'Bearer synthetic-operator-token'}
    metrics = c.get('/internal/metrics', headers=headers)
    assert metrics.status_code == 200 and 'pesopilot_requests_total' in metrics.text
    traces = c.get('/internal/traces', headers=headers)
    assert traces.status_code == 200 and 'PRIVATE_FINANCIAL_VALUE' not in traces.text
    assert 'token' not in traces.text and len(traces.json()) <= 500
    assert c.get('/internal/alerts', headers=headers).status_code == 200


def test_secret_file_injection_and_conflict(tmp_path, monkeypatch):
    from app.db import Settings
    import pytest
    secret = tmp_path / 'secret'
    secret.write_text('synthetic-file-value\n')
    monkeypatch.delenv('OIDC_CLIENT_SECRET', raising=False)
    monkeypatch.setenv('OIDC_CLIENT_SECRET_FILE', str(secret))
    assert Settings(_env_file=None).oidc_client_secret == 'synthetic-file-value'  # pragma: allowlist secret -- synthetic secret-file fixture
    monkeypatch.setenv('OIDC_CLIENT_SECRET', 'synthetic-environment-value')
    with pytest.raises(ValueError):
        Settings(_env_file=None)
