from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.providers.base import ProviderResult, ProviderSource
from app.providers.sec_def14a import extract_def14a_profile
from app.providers.sec_profile_parsers import extract_10k_description


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ticker_aliases(ticker: str) -> set[str]:
    return {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}


def _address_line(address: dict[str, Any] | None) -> str | None:
    if not address:
        return None
    parts = [
        address.get("street1"),
        address.get("street2"),
    ]
    joined = ", ".join(str(part) for part in parts if part)
    return joined or None


def _city_state_postal(address: dict[str, Any] | None) -> str | None:
    if not address:
        return None
    parts = [
        address.get("city"),
        address.get("stateOrCountry"),
        address.get("zipCode"),
    ]
    joined = ", ".join(str(part) for part in parts if part)
    return joined or None


def _country(address: dict[str, Any] | None) -> str | None:
    if not address:
        return None
    return address.get("stateOrCountryDescription") or address.get("stateOrCountry")


def _source_url(cik: str, accession: str, document: str) -> str:
    return SEC_FILING_URL.format(
        cik=int(cik),
        accession=accession.replace("-", ""),
        document=document,
    )


def _recent_filings(
    submissions: dict[str, Any],
    cik: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []

    def value_at(field: str, index: int) -> str | None:
        values = recent.get(field) or []
        value = values[index] if index < len(values) else None
        return value or None

    filings: list[dict[str, Any]] = []
    for index, form in enumerate(forms):
        if not form:
            continue
        accession = value_at("accessionNumber", index)
        document = value_at("primaryDocument", index)
        filings.append(
            {
                "form": form,
                "filing_date": value_at("filingDate", index),
                "report_date": value_at("reportDate", index),
                "description": value_at("primaryDocDescription", index)
                or f"{form} filing",
                "accession_number": accession,
                "source_url": (
                    _source_url(cik, accession, document)
                    if accession and document
                    else None
                ),
            }
        )
        if len(filings) >= limit:
            break
    return filings


def latest_filing(
    submissions: dict[str, Any],
    accepted_forms: set[str],
    *,
    cik: str,
) -> dict[str, str] | None:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []

    def value_at(field: str, index: int) -> str:
        values = recent.get(field) or []
        return values[index] if index < len(values) else ""

    for index, form in enumerate(forms):
        if form not in accepted_forms:
            continue
        accession = value_at("accessionNumber", index)
        document = value_at("primaryDocument", index)
        if not accession or not document:
            continue
        return {
            "form": form,
            "accession": accession,
            "document": document,
            "filing_date": value_at("filingDate", index),
            "report_date": value_at("reportDate", index),
            "source_url": _source_url(cik, accession, document),
        }
    return None


class SecProfileProvider:
    def __init__(self, user_agent: str, timeout_seconds: float = 8) -> None:
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self.timeout_seconds = timeout_seconds

    def fetch(self, ticker: str) -> ProviderResult:
        fetched_at = _utc_now()
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                ticker_response = client.get(SEC_TICKERS_URL)
                ticker_response.raise_for_status()
                ticker_payload = ticker_response.json()
                company = next(
                    (
                        row
                        for row in ticker_payload.values()
                        if str(row.get("ticker", "")).upper()
                        in _ticker_aliases(ticker)
                    ),
                    None,
                )
                if company is None:
                    return ProviderResult(
                        data=None,
                        warnings=[
                            f"SEC does not list {ticker} in its ticker mapping."
                        ],
                    )

                cik = f"{int(company['cik_str']):010d}"
                submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik)
                submissions_response = client.get(submissions_url)
                submissions_response.raise_for_status()
                submissions = submissions_response.json()
                annual_filing = latest_filing(
                    submissions,
                    {"10-K", "20-F", "40-F"},
                    cik=cik,
                )
                proxy_filing = latest_filing(
                    submissions,
                    {"DEF 14A"},
                    cik=cik,
                )
                annual_description = None
                def14a_profile = {
                    "key_executives": [],
                    "executive_compensation": [],
                    "governance": {
                        "directors": [],
                        "committees": [],
                        "voting_matters": [],
                        "notes": [],
                    },
                    "unavailable": ["Latest DEF 14A filing not found"],
                }
                filing_sources: list[ProviderSource] = []
                filing_warnings: list[str] = []
                if annual_filing is not None:
                    try:
                        annual_response = client.get(annual_filing["source_url"])
                        annual_response.raise_for_status()
                        annual_description = extract_10k_description(
                            annual_response.text,
                            annual_filing,
                        )
                        filing_sources.append(
                            ProviderSource(
                                provider=f"SEC {annual_filing['form']}",
                                source_url=annual_filing["source_url"],
                                source_timestamp=annual_filing.get("filing_date")
                                or None,
                                fetched_at=fetched_at,
                            )
                        )
                    except httpx.HTTPError as exc:
                        filing_warnings.append(
                            "SEC annual filing request failed: "
                            f"{exc.__class__.__name__}."
                        )
                if proxy_filing is not None:
                    try:
                        proxy_response = client.get(proxy_filing["source_url"])
                        proxy_response.raise_for_status()
                        def14a_profile = extract_def14a_profile(
                            proxy_response.text,
                            proxy_filing,
                        )
                        filing_sources.append(
                            ProviderSource(
                                provider="SEC DEF 14A",
                                source_url=proxy_filing["source_url"],
                                source_timestamp=proxy_filing.get("filing_date")
                                or None,
                                fetched_at=fetched_at,
                            )
                        )
                    except httpx.HTTPError as exc:
                        filing_warnings.append(
                            "SEC DEF 14A filing request failed: "
                            f"{exc.__class__.__name__}."
                        )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return ProviderResult(
                data=None,
                warnings=[
                    f"SEC profile provider request failed: {exc.__class__.__name__}."
                ],
            )

        business_address = submissions.get("addresses", {}).get("business")
        mailing_address = submissions.get("addresses", {}).get("mailing")
        address = business_address or mailing_address
        exchange = next(iter(submissions.get("exchanges") or []), None)
        listed_ticker = next(iter(submissions.get("tickers") or []), ticker)
        latest_filing_date = max(
            (
                filing.get("filing_date")
                for filing in _recent_filings(submissions, cik, 10)
                if filing.get("filing_date")
            ),
            default=None,
        )

        return ProviderResult(
            data={
                "cik": cik,
                "company_name": submissions.get("name") or company.get("title"),
                "normalized_ticker": listed_ticker,
                "exchange": exchange,
                "contact": {
                    "street_address": _address_line(address),
                    "city_state_postal_code": _city_state_postal(address),
                    "country": _country(address),
                    "phone_number": submissions.get("phone"),
                    "company_website": None,
                },
                "classification": {
                    "sector": (
                        f"SIC {submissions['sic']}"
                        if submissions.get("sic")
                        else None
                    ),
                    "industry": submissions.get("sicDescription"),
                    "full_time_employees": None,
                    "founded": None,
                    "headquarters_region": _country(address),
                },
                "description": None,
                "annual_description": annual_description,
                "def14a": def14a_profile,
                "recent_filings": _recent_filings(submissions, cik),
            },
            sources=[
                ProviderSource(
                    provider="SEC EDGAR Submissions",
                    source_url=submissions_url,
                    source_timestamp=latest_filing_date,
                    fetched_at=fetched_at,
                )
            ]
            + filing_sources,
            warnings=filing_warnings,
        )
