from dataclasses import replace
import importlib

import pytest
from defusedxml.common import DefusedXmlException
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import ApiSecurityController
from app.main import app
from app.api.routes.valuation import get_asset_based, get_ddm, get_relative
from app.providers.sec_holders import parse_ownership_xml
from app.services.telemetry import _parse_latest_10y_from_xml


main_module = importlib.import_module("app.main")


def _request(peer: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/stocks/MSFT/quote",
            "headers": headers,
            "client": (peer, 1234),
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        }
    )


def test_forwarded_ip_is_used_only_from_a_trusted_proxy() -> None:
    settings = replace(get_settings(), trusted_proxy_cidrs=("127.0.0.1/32",))
    controller = ApiSecurityController(settings)

    assert controller.client_ip(_request("203.0.113.10", "198.51.100.7")) == "203.0.113.10"
    assert controller.client_ip(_request("127.0.0.1", "198.51.100.7")) == "198.51.100.7"


def test_vercel_forwarded_ip_requires_vercel_runtime_and_marker(monkeypatch) -> None:
    controller = ApiSecurityController(get_settings())
    request = _request("203.0.113.10", "198.51.100.7")
    request.headers.__dict__["_list"].extend(
        [(b"x-vercel-id", b"iad1::abc"), (b"x-vercel-forwarded-for", b"192.0.2.9")]
    )

    monkeypatch.delenv("VERCEL", raising=False)
    assert controller.client_ip(request) == "203.0.113.10"
    monkeypatch.setenv("VERCEL", "1")
    assert controller.client_ip(request) == "192.0.2.9"


def test_token_bucket_rejects_requests_over_the_limit() -> None:
    controller = ApiSecurityController(get_settings())

    assert controller.consume("198.51.100.1", "test", 2)[0] is True
    assert controller.consume("198.51.100.1", "test", 2)[0] is True
    allowed, remaining, retry_after = controller.consume("198.51.100.1", "test", 2)

    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1


def test_security_headers_are_applied_and_image_proxy_is_removed() -> None:
    client = TestClient(app)

    health = client.get("/health")
    removed_proxy = client.get(
        "/api/news/proxy-image",
        params={"url": "http://169.254.169.254/latest/meta-data"},
    )

    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in health.headers["content-security-policy"]
    assert health.headers["x-request-id"]
    assert removed_proxy.status_code == 404


def test_rate_limit_response_is_stable_and_machine_readable(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module._security,
        "consume",
        lambda _client_ip, _group, _limit: (False, 0, 7),
    )

    response = TestClient(app).get("/api/stocks/MSFT/quote")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json()["detail"] == {
        "code": "rate_limited",
        "message": "Too many requests. Try again after the indicated delay.",
        "retry_after_seconds": 7,
        "request_id": response.headers["x-request-id"],
    }


@pytest.mark.parametrize("parser", [_parse_latest_10y_from_xml])
def test_treasury_xml_rejects_entities(parser) -> None:
    payload = '<!DOCTYPE root [<!ENTITY xxe "expanded">]><root>&xxe;</root>'
    with pytest.raises(DefusedXmlException):
        parser(payload)


def test_sec_ownership_xml_rejects_entities() -> None:
    payload = '<!DOCTYPE root [<!ENTITY xxe "expanded">]><root>&xxe;</root>'
    with pytest.raises(DefusedXmlException):
        parse_ownership_xml(payload, {})


def test_valuation_query_guards_reject_non_finite_and_oversized_lists() -> None:
    non_finite = get_asset_based("MSFT", total_assets=float("inf"))
    dividends = get_ddm("MSFT", historical_dividends=[1.0] * 101)
    peers = get_relative("MSFT", included_peer_symbols=["AAPL"] * 21)

    assert non_finite["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"
    assert dividends["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"
    assert peers["underlying_assumptions"]["error_code"] == "VALUATION_INPUT_INVALID"
