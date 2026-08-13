from app.providers import nasdaq
from app.providers.nasdaq import NasdaqMarketProvider


class FakeHistoricalResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "data": {
                "symbol": "MSFT",
                "tradesTable": {
                    "rows": [
                        {
                            "date": "06/18/2026",
                            "close": "$379.40",
                            "volume": "59,714,160",
                            "open": "$377.82",
                            "high": "$381.37",
                            "low": "$373.28",
                        },
                        {
                            "date": "06/17/2026",
                            "close": "$378.91",
                            "volume": "50,000,000",
                            "open": "$376.00",
                            "high": "$380.00",
                            "low": "$375.00",
                        },
                    ]
                },
            }
        }


class FakeSummaryResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "data": {
                "summaryData": {
                    "Exchange": {"value": "NASDAQ-GS"},
                    "Sector": {"value": "Technology"},
                    "Industry": {"value": "Software"},
                    "MarketCap": {"value": "2,800,000,000,000"},
                }
            }
        }


class FakeDividendsResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "data": {
                "dividends": {
                    "rows": [
                        {
                            "exOrEffDate": "05/11/2026",
                            "type": "Cash",
                            "amount": "$0.27",
                            "declarationDate": "04/30/2026",
                            "paymentDate": "05/14/2026",
                            "currency": "USD",
                        }
                    ]
                }
            }
        }


def test_nasdaq_provider_normalizes_historical_rows(monkeypatch):
    nasdaq._structural_cache.clear()
    monkeypatch.setattr(
        nasdaq.httpx,
        "get",
        lambda url, *args, **kwargs: (
            FakeSummaryResponse()
            if url.endswith("/summary")
            else FakeDividendsResponse()
            if url.endswith("/dividends")
            else FakeHistoricalResponse()
        ),
    )
    import app.providers.yahoo as yahoo
    monkeypatch.setattr(
        yahoo,
        "get_yahoo_quote",
        lambda ticker: {"regularMarketPrice": 379.4, "marketState": "REGULAR"}
    )

    result = NasdaqMarketProvider().fetch("MSFT")

    assert result.data is not None
    assert result.data["quote"]["price"] == 379.4
    assert result.data["quote"]["previous_close"] == 378.91
    assert result.data["quote"]["range_label"] == "Day range"
    assert result.data["interval"] == "daily"
    assert len(result.data["price_history"]) == 2
    assert result.data["overview"]["market_cap"] == 2_800_000_000_000
    assert result.data["overview"]["exchange"] == "NASDAQ-GS"
    assert result.data["dividends"][0]["amount"] == 0.27
    assert result.data["dividend_coverage"] == "reported_events"
    assert result.sources[0].provider == "Nasdaq"
    assert result.sources[-1].provider == "Nasdaq Dividends"
