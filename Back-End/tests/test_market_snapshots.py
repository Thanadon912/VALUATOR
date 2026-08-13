from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.routes import quote as quote_route
from app.main import app
from app.models import LiveQuoteData, LiveQuoteResponse, SourceRecord
from app.services import market_snapshots
from app.services.market_snapshots import SecCompanyNames


def _quote(
    ticker: str,
    *,
    price: float | None = 100.0,
    status: str = "success",
) -> LiveQuoteResponse:
    return LiveQuoteResponse(
        ticker=ticker,
        status=status,
        as_of="2026-07-26T12:00:00+00:00",
        data=LiveQuoteData(
            symbol=ticker,
            price=price,
            change=1.5 if price is not None else None,
            change_percent=1.25 if price is not None else None,
            currency="USD",
        ),
        sources=[
            SourceRecord(
                provider="Quote Provider",
                source_url="https://example.test/quote",
                source_timestamp="2026-07-26T12:00:00+00:00",
                fetched_at="2026-07-26T12:00:01+00:00",
            )
        ],
    )


def _sec_names(names: dict[str, str]) -> SecCompanyNames:
    return SecCompanyNames(
        names=names,
        source=SourceRecord(
            provider="SEC Company Tickers",
            source_url=market_snapshots.SEC_TICKERS_URL,
            source_timestamp=None,
            fetched_at="2026-07-26T11:00:00+00:00",
        ),
    )


def test_snapshots_deduplicate_and_preserve_first_seen_order(monkeypatch) -> None:
    monkeypatch.setattr(
        market_snapshots,
        "get_sec_company_names",
        lambda: _sec_names({"MSFT": "MICROSOFT CORP", "AAPL": "Apple Inc."}),
    )
    quote_loader = Mock(side_effect=lambda ticker: _quote(ticker))
    monkeypatch.setattr(quote_route, "get_live_quote", quote_loader)

    response = TestClient(app).get(
        "/api/stocks/snapshots",
        params={"tickers": "msft,AAPL,MSFT"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert [item["ticker"] for item in payload["data"]] == ["MSFT", "AAPL"]
    assert payload["data"][0]["company_name"] == "MICROSOFT CORP"
    assert payload["data"][0]["price"] == 100.0
    assert [source["provider"] for source in payload["data"][0]["sources"]] == [
        "Quote Provider",
        "SEC Company Tickers",
    ]
    assert {call.args[0] for call in quote_loader.call_args_list} == {
        "MSFT",
        "AAPL",
    }


def test_snapshots_reject_more_than_twenty_unique_tickers(monkeypatch) -> None:
    builder = Mock(side_effect=AssertionError("provider must not be called"))
    monkeypatch.setattr(quote_route, "build_market_snapshots", builder)
    tickers = ",".join(f"T{index}" for index in range(21))

    response = TestClient(app).get(
        "/api/stocks/snapshots",
        params={"tickers": tickers},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "A maximum of 20 unique tickers is allowed per request."
    )
    builder.assert_not_called()


def test_snapshots_reject_invalid_or_empty_entries() -> None:
    client = TestClient(app)

    invalid = client.get(
        "/api/stocks/snapshots",
        params={"tickers": "AAPL,$BAD"},
    )
    empty = client.get(
        "/api/stocks/snapshots",
        params={"tickers": "AAPL,,MSFT"},
    )

    assert invalid.status_code == 422
    assert "Ticker must be" in invalid.json()["detail"]
    assert empty.status_code == 422
    assert "without empty values" in empty.json()["detail"]


def test_snapshots_expose_partial_and_unavailable_items(monkeypatch) -> None:
    monkeypatch.setattr(
        market_snapshots,
        "get_sec_company_names",
        lambda: _sec_names({"MISSING": "Missing Price Corp"}),
    )

    def quote_loader(ticker: str) -> LiveQuoteResponse:
        if ticker == "AAPL":
            return _quote(ticker)
        return _quote(ticker, price=None, status="unavailable")

    result = market_snapshots.build_market_snapshots(
        ["AAPL", "MISSING"],
        quote_loader,
    )

    assert result.status == "partial"
    assert result.data[0].status == "partial"
    assert result.data[0].company_name is None
    assert result.data[0].price == 100.0
    assert result.data[0].warnings == ["SEC company name unavailable for AAPL."]
    assert result.data[1].status == "unavailable"
    assert result.data[1].company_name == "Missing Price Corp"
    assert result.data[1].price is None


def test_sec_company_name_mapping_is_cached_for_twenty_four_hours(monkeypatch) -> None:
    market_snapshots._sec_company_names_cache = None
    response = Mock()
    response.json.return_value = {
        "0": {"ticker": "BRK-B", "title": "Berkshire Hathaway Inc."}
    }
    response.raise_for_status.return_value = None
    client = Mock()
    client.get.return_value = response
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=client)
    context_manager.__exit__ = Mock(return_value=False)
    client_factory = Mock(return_value=context_manager)
    monkeypatch.setattr(market_snapshots.httpx, "Client", client_factory)

    first = market_snapshots.get_sec_company_names()
    second = market_snapshots.get_sec_company_names()

    assert first.names["BRK-B"] == "Berkshire Hathaway Inc."
    assert first.names["BRK.B"] == "Berkshire Hathaway Inc."
    assert second is first
    client.get.assert_called_once_with(market_snapshots.SEC_TICKERS_URL)
    market_snapshots._sec_company_names_cache = None
