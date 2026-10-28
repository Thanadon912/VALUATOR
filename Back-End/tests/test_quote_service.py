from app.providers.base import ProviderResult, ProviderSource
from app.services import quote as quote_service


class FakeAlpacaProvider:
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_latest(self, ticker: str) -> ProviderResult:
        return ProviderResult(
            data={
                "symbol": ticker,
                "price": 200.0,
                "timestamp": "2026-07-06T20:30:00+00:00",
                "market_state": "POST",
                "extended_price": 200.0,
                "extended_hours_timestamp": "2026-07-06T20:30:00+00:00",
            },
            sources=[
                ProviderSource(
                    provider="Alpaca Trade",
                    source_url="https://data.alpaca.markets/v2/stocks/trades/latest",
                    source_timestamp="2026-07-06T20:30:00+00:00",
                    fetched_at="2026-07-06T20:30:01+00:00",
                )
            ],
        )


class FakeNasdaqProvider:
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str) -> ProviderResult:
        return ProviderResult(
            data={
                "quote": {
                    "previous_close": 190.0,
                    "price": 191.0,
                    "latest_trading_day": "2026-07-06",
                },
                "overview": {
                    "currency": "USD",
                    "exchange": "NASDAQ",
                },
            },
            sources=[
                ProviderSource(
                    provider="Nasdaq",
                    source_url="https://api.nasdaq.com/api/quote/AAPL/historical",
                    source_timestamp="2026-07-06",
                    fetched_at="2026-07-06T20:30:01+00:00",
                )
            ],
        )


def test_live_quote_response_uses_alpaca_before_yahoo(monkeypatch):
    monkeypatch.setattr(quote_service, "AlpacaMarketDataProvider", FakeAlpacaProvider)
    monkeypatch.setattr(quote_service, "NasdaqMarketProvider", FakeNasdaqProvider)
    monkeypatch.setattr(quote_service, "get_yahoo_quote", lambda ticker: {})

    response = quote_service.build_live_quote_response("AAPL")

    assert response.status == "success"
    assert response.data.price == 200.0
    assert response.data.previous_close == 190.0
    assert response.data.change == 10.0
    assert response.data.change_percent == 10.0 / 190.0 * 100
    assert response.data.market_state == "POST"
    assert response.data.extended_price == 200.0
    assert response.data.extended_change == 10.0
    assert response.data.extended_change_percent == 10.0 / 190.0 * 100
    assert response.sources[0].provider == "Alpaca Trade"


def test_validate_ticker_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Valid via Yahoo mock
    monkeypatch.setattr(
        "app.api.routes.quote.get_yahoo_quote",
        lambda t: {"regularMarketPrice": 150.0} if t == "AAPL" else {},
    )
    res = client.get("/api/stocks/AAPL/validate")
    assert res.status_code == 200
    assert res.json() == {"valid": True, "ticker": "AAPL"}

    # Invalid ticker mock
    monkeypatch.setattr(
        "app.api.routes.quote.AlpacaMarketDataProvider",
        lambda timeout_seconds: type("Fake", (), {"fetch_latest": lambda self, t: type("R", (), {"data": None})()})(),
    )
    res_fake = client.get("/api/stocks/FAKE/validate")
    assert res_fake.status_code == 200
    assert res_fake.json() == {"valid": False, "ticker": "FAKE"}
