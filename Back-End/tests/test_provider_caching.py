from concurrent.futures import ThreadPoolExecutor
from time import sleep
from unittest.mock import Mock

from app.providers import alpha_vantage, finnhub_metrics, finnhub_profile, nasdaq
from app.providers.alpha_vantage import AlphaVantageOverviewProvider
from app.providers.base import ProviderResult
from app.providers.finnhub_metrics import FinnhubMetricProvider
from app.providers.finnhub_profile import FinnhubProfileProvider
from app.providers.nasdaq import NasdaqMarketProvider
from app.providers.yahoo import YahooQuoteProvider


def test_yahoo_quote_cache_coalesces_concurrent_calls(monkeypatch):
    provider = YahooQuoteProvider()
    upstream = Mock(side_effect=lambda ticker: (sleep(0.02), {"ticker": ticker})[1])
    monkeypatch.setattr(provider, "_fetch_quote", upstream)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(provider.get_quote, ["aapl"] * 8))

    assert upstream.call_count == 1
    assert results == [{"ticker": "AAPL"}] * 8


def test_yahoo_summary_metrics_cache_reuses_structural_result(monkeypatch):
    provider = YahooQuoteProvider()
    upstream = Mock(return_value={"trailingPE": 20.0})
    monkeypatch.setattr(provider, "_fetch_quote_summary_metrics", upstream)

    assert provider.get_quote_summary_metrics("msft")["trailingPE"] == 20.0
    assert provider.get_quote_summary_metrics("MSFT")["trailingPE"] == 20.0
    upstream.assert_called_once_with("MSFT")


def test_finnhub_metric_cache_coalesces_concurrent_calls(monkeypatch):
    finnhub_metrics._metric_cache.clear()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"metric": {"beta": 1.2}}
    upstream = Mock(side_effect=lambda *args, **kwargs: (sleep(0.02), response)[1])
    monkeypatch.setattr(finnhub_metrics.httpx, "get", upstream)
    provider = FinnhubMetricProvider(api_key="test")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(provider.fetch, ["aapl"] * 8))

    assert upstream.call_count == 1
    assert all(result.data == {"beta": 1.2} for result in results)


def test_alpha_vantage_success_is_cached_and_failure_is_not(monkeypatch):
    alpha_vantage._overview_cache.clear()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"Symbol": "AAPL", "Beta": "1.1"}
    upstream = Mock(return_value=response)
    monkeypatch.setattr(alpha_vantage.httpx, "get", upstream)
    provider = AlphaVantageOverviewProvider(api_key="test")

    assert provider.fetch("aapl").data["beta"] == 1.1
    assert provider.fetch("AAPL").data["beta"] == 1.1
    assert upstream.call_count == 1


def test_finnhub_structural_profile_skips_quote_and_calendar_and_is_cached(monkeypatch):
    finnhub_profile._structural_profile_cache.clear()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "country": "US",
        "currency": "USD",
        "finnhubIndustry": "Technology",
    }
    upstream = Mock(return_value=response)
    provider = FinnhubProfileProvider(api_key="test")
    monkeypatch.setattr(provider, "_get", upstream)

    first = provider.fetch_structural_profile("aapl")
    second = provider.fetch_structural_profile("AAPL")

    assert first.data == second.data
    assert first.data["fields"]["country"]["value"] == "US"
    upstream.assert_called_once_with(finnhub_profile.FINNHUB_PROFILE_URL, {"symbol": "AAPL"})


def test_nasdaq_structural_cache_coalesces_concurrent_refreshes(monkeypatch):
    nasdaq._structural_cache.clear()
    provider = NasdaqMarketProvider()
    calls = 0

    def fetch_structural(ticker):
        nonlocal calls
        calls += 1
        sleep(0.02)
        payload = {"ticker": ticker}
        with nasdaq._cache_lock:
            nasdaq._structural_cache[ticker] = (nasdaq.monotonic(), payload)
        return payload

    monkeypatch.setattr(provider, "_fetch_structural", fetch_structural)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(provider._get_structural, ["AAPL"] * 8))

    assert calls == 1
    assert results == [{"ticker": "AAPL"}] * 8
