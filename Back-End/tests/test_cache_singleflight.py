from concurrent.futures import ThreadPoolExecutor
from time import sleep
from unittest.mock import Mock

from app.api.routes import valuation
from app.providers import sec
from app.providers.base import ProviderResult
from app.services import international, telemetry


def test_sec_company_refresh_is_singleflight(monkeypatch):
    sec._company_cache.clear()
    provider = sec.SecCompanyFactsProvider(user_agent="test@example.com")
    calls = 0

    def fetch_uncached(ticker):
        nonlocal calls
        calls += 1
        sleep(0.02)
        result = ProviderResult(data={"ticker": ticker})
        with sec._cache_lock:
            sec._company_cache[ticker] = (sec.monotonic(), result)
        return result

    monkeypatch.setattr(provider, "_fetch_uncached", fetch_uncached)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(provider.fetch, ["aapl"] * 8))

    assert calls == 1
    assert all(result.data == {"ticker": "AAPL"} for result in results)


def test_fx_refresh_is_singleflight(monkeypatch):
    international._fx_cache.clear()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "chart": {"result": [{
            "timestamp": [1_700_000_000],
            "indicators": {"quote": [{"close": [0.031]}]},
        }]}
    }
    upstream = Mock(side_effect=lambda *args, **kwargs: (sleep(0.02), response)[1])
    monkeypatch.setattr(international.httpx, "get", upstream)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(international.fetch_usd_fx_rate, ["twd"] * 8))

    assert upstream.call_count == 1
    assert all(result["rate"] == 0.031 for result in results)


def test_treasury_sync_and_async_callers_share_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(telemetry, "_risk_free_cache_updated_at", -float("inf"))
    monkeypatch.setattr(telemetry, "RISK_FREE_CACHE_FILE", tmp_path / "risk-free.json")
    monkeypatch.setattr(telemetry, "_parse_latest_10y_from_xml", lambda text: (0.042, "2026-07-30"))
    response = Mock(text="xml")
    response.raise_for_status.return_value = None
    client = Mock()
    client.get.side_effect = lambda *args, **kwargs: (sleep(0.02), response)[1]
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(telemetry.httpx, "Client", Mock(return_value=context))

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: telemetry.fetch_treasury_risk_free_rate_sync(), range(8)))

    assert client.get.call_count == 1
    assert results == [0.042] * 8


def test_relative_peer_metrics_are_shared_across_target_tickers(monkeypatch):
    valuation._relative_peer_cache.clear()
    valuation._relative_metric_cache.clear()
    calls = 0

    def specs(_ticker):
        return [{
            "symbol": "MSFT", "source_symbol": "MSFT", "name": "Microsoft",
            "overlap_score": 1, "reason": "test",
        }]

    def load_metrics(_ticker):
        nonlocal calls
        calls += 1
        sleep(0.02)
        return {"pe": 20.0, "pb": 5.0, "ev_ebitda": 12.0,
                "market_cap": 1.0, "metric_sources": {}}

    monkeypatch.setattr(valuation, "_default_relative_peer_specs", specs)
    monkeypatch.setattr(valuation, "_load_relative_peer_metrics", load_metrics)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(valuation.build_relative_peers, ["AAPL", "AMZN"]))

    assert calls == 1
    assert all(result[0]["pe"] == 20.0 for result in results)
