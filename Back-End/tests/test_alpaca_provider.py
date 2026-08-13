from app.providers import alpaca
from app.providers.alpaca import AlpacaMarketDataProvider
from pytest import approx


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_alpaca_provider_prefers_latest_trade_and_marks_pre_market(monkeypatch):
    requests: list[tuple[str, dict, dict]] = []

    def fake_get(url, *, params, headers, timeout):
        requests.append((url, params, headers))
        if url == alpaca.ALPACA_LATEST_TRADES_URL:
            return FakeResponse(
                {
                    "trades": {
                        "AAPL": {
                            "p": 211.13,
                            "t": "2026-07-06T12:00:00.123456789Z",
                        }
                    }
                }
            )
        return FakeResponse(
            {
                "quotes": {
                    "AAPL": {
                        "bp": 211.0,
                        "ap": 211.2,
                        "bs": 3,
                        "as": 5,
                        "t": "2026-07-06T12:00:01Z",
                    }
                }
            }
        )

    monkeypatch.setattr(alpaca.httpx, "get", fake_get)

    result = AlpacaMarketDataProvider(
        api_key="key",
        api_secret="secret",
    ).fetch_latest("aapl")

    assert result.data["symbol"] == "AAPL"
    assert result.data["price"] == 211.13
    assert result.data["price_source"] == "trade"
    assert result.data["market_state"] == "PRE"
    assert result.data["extended_price"] == 211.13
    assert result.sources[0].provider == "Alpaca Trade"
    assert requests[0][0] == "https://data.alpaca.markets/v2/stocks/trades/latest"
    assert requests[0][1] == {"symbols": "AAPL", "feed": "iex"}
    assert requests[0][2]["APCA-API-KEY-ID"] == "key"
    assert requests[0][2]["APCA-API-SECRET-KEY"] == "secret"


def test_alpaca_provider_uses_quote_midpoint_when_trade_missing(monkeypatch):
    def fake_get(url, *, params, headers, timeout):
        if url == alpaca.ALPACA_LATEST_TRADES_URL:
            return FakeResponse({"trades": {}})
        return FakeResponse(
            {
                "quotes": {
                    "MSFT": {
                        "bp": 420.1,
                        "ap": 420.3,
                        "t": "2026-07-06T14:00:00Z",
                    }
                }
            }
        )

    monkeypatch.setattr(alpaca.httpx, "get", fake_get)

    result = AlpacaMarketDataProvider(
        api_key="key",
        api_secret="secret",
        data_feed="iex",
    ).fetch_latest("MSFT")

    assert result.data["price"] == approx(420.2)
    assert result.data["price_source"] == "quote"
    assert result.data["market_state"] == "REGULAR"
    assert result.data["extended_price"] is None
    assert result.sources[0].provider == "Alpaca Quote"
    assert result.warnings == [
        "Alpaca latest trade unavailable; using latest quote price."
    ]
