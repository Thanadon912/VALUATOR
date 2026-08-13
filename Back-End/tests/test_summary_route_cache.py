from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from app.api.routes import summary as summary_route


def _response(ticker: str) -> SimpleNamespace:
    return SimpleNamespace(ticker=ticker)


def test_summary_cache_coalesces_concurrent_requests() -> None:
    summary_route._cache.clear()
    summary_route._ticker_locks.clear()

    with patch.object(
        summary_route,
        "build_summary_response",
        side_effect=lambda ticker: _response(ticker),
    ) as build:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(summary_route.get_summary, ["msft"] * 8))

    assert build.call_count == 1
    assert all(result.ticker == "MSFT" for result in results)


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Summary & Fundamentals",
    feature="Caching",
    story="Ticker Scope Integrity",
    priority="P0",
    severity="critical",
    layer="backend-api",
    test_id="VAL-BE-API-SUM-002"
)
def test_summary_cache_is_scoped_by_ticker() -> None:
    summary_route._cache.clear()
    summary_route._ticker_locks.clear()

    with patch.object(
        summary_route,
        "build_summary_response",
        side_effect=lambda ticker: _response(ticker),
    ) as build:
        assert summary_route.get_summary("MSFT").ticker == "MSFT"
        assert summary_route.get_summary("AAPL").ticker == "AAPL"

    assert build.call_count == 2
