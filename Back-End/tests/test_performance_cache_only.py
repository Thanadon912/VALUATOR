import asyncio
from contextlib import contextmanager
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes import news as news_route
from app.api.routes import quote as quote_route
from app.api.routes import summary as summary_route
from app.api.routes import valuation
from app.services import market_snapshots
from app.services.market_snapshots import SecCompanyNames
from app.core.performance_cache import (
    reset_performance_cache_only,
    set_performance_cache_only,
)
from app.main import app
from app.models import LiveQuoteData, LiveQuoteResponse


@contextmanager
def _cache_only_context():
    token = set_performance_cache_only(True)
    try:
        yield
    finally:
        reset_performance_cache_only(token)


@pytest.fixture(autouse=True)
def _clear_route_caches():
    summary_route._cache.clear()
    summary_route._ticker_locks.clear()
    quote_route._cache.clear()
    quote_route._ticker_locks.clear()
    news_route._response_cache.clear()
    valuation._valuation_input_cache.clear()
    valuation._valuation_telemetry_cache.clear()
    valuation._relative_peer_cache.clear()
    yield
    summary_route._cache.clear()
    summary_route._ticker_locks.clear()
    quote_route._cache.clear()
    quote_route._ticker_locks.clear()
    news_route._response_cache.clear()
    valuation._valuation_input_cache.clear()
    valuation._valuation_telemetry_cache.clear()
    valuation._relative_peer_cache.clear()


def _quote_response(price: float, ticker: str = "MSFT") -> LiveQuoteResponse:
    return LiveQuoteResponse(
        ticker=ticker,
        status="success",
        as_of="2026-07-18T00:00:00+00:00",
        data=LiveQuoteData(symbol=ticker, price=price),
    )


def test_snapshot_cache_only_context_never_escapes_to_provider_threads(
    monkeypatch,
) -> None:
    stale_at = monotonic() - quote_route.LIVE_QUOTE_CACHE_TTL_SECONDS - 1
    quote_route._cache.update(
        {
            "MSFT": (stale_at, _quote_response(123.0, "MSFT")),
            "AAPL": (stale_at, _quote_response(234.0, "AAPL")),
        }
    )
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)
    monkeypatch.setattr(
        market_snapshots,
        "get_sec_company_names",
        lambda: SecCompanyNames(names={}, warnings=("names unavailable",)),
    )

    with _cache_only_context():
        response = quote_route.get_stock_snapshots("MSFT,AAPL")

    assert [item.ticker for item in response.data] == ["MSFT", "AAPL"]
    assert [item.price for item in response.data] == [123.0, 234.0]
    provider.assert_not_called()


def test_snapshot_cache_only_header_serves_stale_quotes_without_provider(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")
    stale_at = monotonic() - quote_route.LIVE_QUOTE_CACHE_TTL_SECONDS - 1
    quote_route._cache.update(
        {
            "MSFT": (stale_at, _quote_response(123.0, "MSFT")),
            "AAPL": (stale_at, _quote_response(234.0, "AAPL")),
        }
    )
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)
    monkeypatch.setattr(
        market_snapshots,
        "get_sec_company_names",
        lambda: SecCompanyNames(names={}, warnings=("names unavailable",)),
    )

    response = TestClient(app).get(
        "/api/stocks/snapshots?tickers=MSFT,AAPL",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )

    assert response.status_code == 200
    assert [item["price"] for item in response.json()["data"]] == [123.0, 234.0]
    provider.assert_not_called()


def test_cache_only_header_is_rejected_when_feature_flag_is_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "false")

    response = TestClient(app).get(
        "/health",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "performance_cache_only_disabled"


def test_cache_only_context_is_reset_after_each_request(monkeypatch) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")
    provider = Mock(return_value=_quote_response(456.0))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)
    client = TestClient(app)

    guarded_response = client.get(
        "/health",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )
    normal_response = client.get("/api/stocks/MSFT/quote")

    assert guarded_response.status_code == 200
    assert normal_response.status_code == 200
    assert normal_response.json()["data"]["price"] == 456.0
    provider.assert_called_once_with("MSFT")


def test_cache_only_header_serves_stale_quote_without_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")
    quote_route._cache["MSFT"] = (
        monotonic() - quote_route.LIVE_QUOTE_CACHE_TTL_SECONDS - 1,
        _quote_response(123.0),
    )
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)

    response = TestClient(app).get(
        "/api/stocks/MSFT/quote",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["price"] == 123.0
    provider.assert_not_called()


def test_cache_only_quote_miss_returns_503_without_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)

    response = TestClient(app).get(
        "/api/stocks/MSFT/quote",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "performance_cache_miss",
        "message": "Required warmed data is not present in this API process.",
        "resource": "quote",
        "cache_key": "MSFT",
    }
    provider.assert_not_called()


def test_normal_quote_request_does_not_reuse_stale_cache(monkeypatch) -> None:
    quote_route._cache["MSFT"] = (
        monotonic() - quote_route.LIVE_QUOTE_CACHE_TTL_SECONDS - 1,
        _quote_response(123.0),
    )
    provider = Mock(return_value=_quote_response(456.0))
    monkeypatch.setattr(quote_route, "build_live_quote_response", provider)

    response = TestClient(app).get("/api/stocks/MSFT/quote")

    assert response.status_code == 200
    assert response.json()["data"]["price"] == 456.0
    provider.assert_called_once_with("MSFT")


def test_summary_cache_only_serves_stale_or_raises_explicit_miss(
    monkeypatch,
) -> None:
    cached = SimpleNamespace(ticker="MSFT")
    summary_route._cache["MSFT"] = (
        monotonic() - summary_route.SUMMARY_CACHE_TTL_SECONDS - 1,
        cached,
    )
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(summary_route, "build_summary_response", provider)

    with _cache_only_context():
        assert summary_route.get_summary("MSFT") is cached
        summary_route._cache.clear()
        with pytest.raises(HTTPException) as exc_info:
            summary_route.get_summary("MSFT")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "performance_cache_miss"
    assert exc_info.value.detail["resource"] == "summary"
    provider.assert_not_called()


def test_news_cache_only_serves_stale_response_without_classification_call(
    monkeypatch,
) -> None:
    cached = news_route.NewsResponse(
        ticker="MSFT",
        articles=[],
        status="success",
    )
    news_route._response_cache["MSFT"] = (
        monotonic() - news_route.NEWS_CACHE_TTL_SECONDS - 1,
        cached,
    )
    classification = Mock(
        side_effect=AssertionError("classification provider must not be called")
    )
    monkeypatch.setattr(news_route, "get_company_classification", classification)

    with _cache_only_context():
        response = asyncio.run(news_route.get_news("MSFT"))

    assert response is cached
    classification.assert_not_called()


def test_news_cache_only_miss_is_explicit() -> None:
    with _cache_only_context():
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(news_route.get_news("MSFT"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "performance_cache_miss"
    assert exc_info.value.detail["resource"] == "news"


def test_valuation_caches_serve_stale_without_provider_calls(monkeypatch) -> None:
    stale_timestamp = monotonic() - max(
        valuation.VALUATION_INPUT_CACHE_TTL_SECONDS,
        valuation.VALUATION_TELEMETRY_CACHE_TTL_SECONDS,
        valuation.RELATIVE_PEER_CACHE_TTL_SECONDS,
    ) - 1
    inputs = {"shares_outstanding": 100.0}
    telemetry = {"current_price": 50.0}
    peers = [{"symbol": "AAPL", "pe": 20.0}]
    valuation._valuation_input_cache["MSFT"] = (stale_timestamp, inputs)
    valuation._valuation_telemetry_cache["MSFT"] = (stale_timestamp, telemetry)
    valuation._relative_peer_cache["MSFT"] = (stale_timestamp, peers)

    input_provider = Mock(side_effect=AssertionError("provider must not be called"))
    telemetry_provider = Mock(side_effect=AssertionError("provider must not be called"))
    peer_provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(valuation, "_load_valuation_inputs", input_provider)
    monkeypatch.setattr(
        valuation,
        "fetch_treasury_risk_free_rate_sync",
        telemetry_provider,
    )
    monkeypatch.setattr(valuation, "_default_relative_peer_specs", peer_provider)

    with _cache_only_context():
        assert valuation.get_valuation_inputs("MSFT") is inputs
        assert valuation.get_valuation_telemetry("MSFT") is telemetry
        assert valuation.build_relative_peers("MSFT") is peers

    input_provider.assert_not_called()
    telemetry_provider.assert_not_called()
    peer_provider.assert_not_called()


def test_cache_only_relative_peers_accepts_warmed_empty_result(
    monkeypatch,
) -> None:
    valuation._relative_peer_cache["MSFT"] = (
        monotonic() - valuation.RELATIVE_PEER_CACHE_TTL_SECONDS - 1,
        [],
    )
    provider = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(valuation, "_default_relative_peer_specs", provider)

    with _cache_only_context():
        assert valuation.build_relative_peers("MSFT") == []

    provider.assert_not_called()


@pytest.mark.parametrize(
    ("getter_name", "resource"),
    [
        ("get_valuation_inputs", "valuation_inputs"),
        ("get_valuation_telemetry", "valuation_telemetry"),
        ("build_relative_peers", "relative_peers"),
    ],
)
def test_valuation_cache_only_misses_are_explicit(getter_name, resource) -> None:
    getter = getattr(valuation, getter_name)
    with _cache_only_context():
        with pytest.raises(HTTPException) as exc_info:
            getter("MSFT")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "performance_cache_miss"
    assert exc_info.value.detail["resource"] == resource


def test_valuation_route_preserves_cache_miss_http_status(monkeypatch) -> None:
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")

    response = TestClient(app).get(
        "/api/v1/valuation/ddm?ticker=MSFT",
        headers={"X-VALUATOR-Cache-Only": "true"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "performance_cache_miss"
    assert response.json()["detail"]["resource"] == "valuation_inputs"


def test_ddm_uses_cached_telemetry_price_in_cache_only_mode(monkeypatch) -> None:
    inputs = {
        "dividends_paid": 20.0,
        "shares_outstanding": 10.0,
        "historical_dividends": [10.0, 15.0, 20.0],
        "net_income": 100.0,
        "adr_ratio": 1.0,
    }
    telemetry = {"cost_of_equity": 0.10, "current_price": 100.0}
    monkeypatch.setattr(valuation, "get_valuation_inputs", lambda ticker: inputs)
    monkeypatch.setattr(valuation, "get_valuation_telemetry", lambda ticker: telemetry)
    monkeypatch.setattr(
        valuation,
        "calculate_ddm_valuation",
        lambda *args: {
            "computed_fair_value": 120.0,
            "annual_dividend_per_share": 2.0,
            "dividend_growth_cagr": 0.03,
            "status": "CALCULATED",
        },
    )
    yahoo = Mock(side_effect=AssertionError("Yahoo must not be called"))
    monkeypatch.setattr(valuation, "get_yahoo_quote", yahoo)

    with _cache_only_context():
        response = valuation.get_ddm("MSFT", historical_dividends=None)

    assert response["valuation_status"] == "CALCULATED"
    assert response["current_price"] == 100.0
    yahoo.assert_not_called()
