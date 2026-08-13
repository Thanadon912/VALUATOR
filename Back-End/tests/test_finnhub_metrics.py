from __future__ import annotations

import httpx

from app.providers import finnhub_metrics
from app.providers.finnhub_metrics import FinnhubMetricProvider


def test_finnhub_metric_warning_does_not_expose_request_token(monkeypatch) -> None:
    finnhub_metrics._metric_cache.clear()
    request = httpx.Request(
        "GET",
        "https://finnhub.io/api/v1/stock/metric",
        params={"symbol": "JPM", "metric": "all", "token": "sensitive-test-token"},
    )
    response = httpx.Response(401, request=request)

    def reject(*args, **kwargs):
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(httpx, "get", reject)
    result = FinnhubMetricProvider(api_key="sensitive-test-token").fetch("JPM")

    assert result.data == {}
    assert result.warnings == ["Finnhub metrics fetch failed: HTTP 401"]
    assert "sensitive-test-token" not in result.warnings[0]
    assert "token=" not in result.warnings[0]
