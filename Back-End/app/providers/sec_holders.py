from __future__ import annotations

import re
from defusedxml import ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from threading import Lock
from time import monotonic
from typing import Any

import httpx

from app.providers.base import ProviderResult, ProviderSource
from app.providers.sec import (
    SEC_COMPANY_FACTS_URL,
    SEC_FILING_URL,
    SEC_SUBMISSIONS_URL,
    SEC_TICKERS_URL,
    _ticker_aliases,
)


HOLDERS_CACHE_TTL_SECONDS = 5 * 60
MAJOR_FORMS = {"DEF 14A", "20-F", "13D", "13D/A", "13G", "13G/A"}
INSIDER_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}
TRANSACTION_CODE_TYPES = {
    "P": "buy",
    "S": "sell",
    "A": "award",
    "M": "exercise",
    "G": "gift",
    "F": "tax_withholding",
    "C": "conversion",
}

_cache_lock = Lock()
_holders_cache: dict[str, tuple[float, ProviderResult]] = {}
_ticker_cache: tuple[float, dict[str, dict[str, Any]]] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _normalize_holder_name(value: str) -> str:
    normalized = _clean_text(value)
    normalized = re.sub(
        r"\(\s*\d+\s+persons?\s*\)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"[\(\[\*†‡]\s*\d+[a-z]?\s*[\)\]]?", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,.;:")
    return normalized


def _parse_number(value: str | None) -> float | None:
    text = _clean_text(value)
    if not text or text in {"—", "-", "N/A", "n/a", "*"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if not negative:
        text = re.sub(r"\(\s*\d+[a-z]?\s*\)\s*$", "", text)
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", ".", "-", "-."}:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative and number > 0 else number


def _parse_shares(value: str | None) -> int | None:
    number = _parse_number(value)
    if number is None:
        return None
    return int(round(number))


def _parse_percent(value: str | None) -> tuple[float | None, str | None]:
    text = _clean_text(value)
    compact = text.lower().replace(" ", "")
    if compact == "*" or "lessthan1%" in compact or "<1%" in compact:
        return None, "<1%"
    number = _parse_number(text)
    if number is None:
        return None, None
    return number, None


def _holder_type(name: str) -> str:
    lower = name.lower()
    if (
        ("all directors" in lower or "all current directors" in lower or "directors and" in lower)
        and "executive officers" in lower
    ):
        return "group"
    if any(
        marker in lower
        for marker in (
            "capital management",
            "asset management",
            "investment management",
            "partners lp",
            "partners, l.p.",
            "fund ",
            "trust",
            "bank",
            "inc.",
            "llc",
            "l.p.",
            "vanguard",
            "blackrock",
        )
    ):
        return "institution"
    return "beneficial_owner"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._sup_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag == "table":
            if self._table_depth == 0:
                self._rows = []
            self._table_depth += 1
        elif self._table_depth and tag == "tr":
            self._row = []
        elif self._table_depth and tag in {"td", "th"}:
            self._cell = []
        elif self._cell is not None and tag == "sup":
            self._sup_depth += 1
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None and self._sup_depth == 0:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "sup" and self._sup_depth:
            self._sup_depth -= 1
        elif self._table_depth and tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif self._table_depth and tag == "tr":
            if self._row and any(self._row):
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0 and self._rows:
                self.tables.append(self._rows)
                self._rows = []


def _extract_as_of_date(text: str) -> str | None:
    patterns = (
        r"as of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"as of\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"as of\s+(\d{4}-\d{2}-\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        value = match.group(1)
        for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _column_indexes(row: list[str]) -> tuple[int, int, int] | None:
    normalized = [cell.lower() for cell in row]
    name_index = next(
        (
            index
            for index, cell in enumerate(normalized)
            if "name" in cell
            or "beneficial owner" in cell
            or "principal stockholder" in cell
        ),
        None,
    )
    shares_index = next(
        (
            index
            for index, cell in enumerate(normalized)
            if "shares" in cell
            or "amount and nature" in cell
            or "number beneficially" in cell
        ),
        None,
    )
    percent_index = next(
        (
            index
            for index, cell in enumerate(normalized)
            if "percent" in cell or "% of" in cell
        ),
        None,
    )
    if name_index is None or shares_index is None or percent_index is None:
        return None
    return name_index, shares_index, percent_index


def parse_major_holders_html(
    html: str,
    filing: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    document_text = _clean_text(re.sub(r"<[^>]+>", " ", html))
    as_of_date = _extract_as_of_date(document_text) or filing.get("report_date")
    records: list[dict[str, Any]] = []

    for table in parser.tables:
        indexes: tuple[int, int, int] | None = None
        header_row = -1
        for row_index, row in enumerate(table[:12]):
            indexes = _column_indexes(row)
            if indexes is not None:
                header_row = row_index
                break
        if indexes is None:
            continue
        name_index, shares_index, percent_index = indexes
        for row in table[header_row + 1 :]:
            if max(indexes) >= len(row):
                continue
            name = _normalize_holder_name(row[name_index])
            if not name or name.lower().startswith(("name", "total")):
                continue
            shares = _parse_shares(row[shares_index])
            percent, display_note = _parse_percent(row[percent_index])
            if shares is None and percent is None and display_note is None:
                continue
            records.append(
                {
                    "holder_name": name,
                    "shares_held": shares,
                    "ownership_percent": percent,
                    "ownership_display_note": display_note,
                    "holder_type": _holder_type(name),
                    "as_of_date": as_of_date,
                    "filing_type": filing["form"],
                    "filing_date": filing["filing_date"],
                    "accession_number": filing["accession"],
                    "source_url": filing["source_url"],
                }
            )

    deduplicated: dict[tuple[str, str | None], dict[str, Any]] = {}
    for record in records:
        key = (
            re.sub(r"[^a-z0-9]", "", record["holder_name"].lower()),
            record["as_of_date"],
        )
        existing = deduplicated.get(key)
        if existing is None or (
            existing["shares_held"] is None and record["shares_held"] is not None
        ):
            deduplicated[key] = record

    holders = list(deduplicated.values())
    group = next(
        (record for record in holders if record["holder_type"] == "group"),
        None,
    )
    if group:
        summary = {
            "insider_shares": group["shares_held"],
            "insider_ownership_percent": group["ownership_percent"],
            "ownership_display_note": group["ownership_display_note"],
            "as_of_date": group["as_of_date"],
            "calculation_method": "reported_group_total",
            "source_url": group["source_url"],
        }
    else:
        insiders = [
            record
            for record in holders
            if record["holder_type"] in {"director", "executive", "insider"}
        ]
        complete = bool(insiders) and all(
            record["shares_held"] is not None for record in insiders
        )
        summary = {
            "insider_shares": (
                sum(record["shares_held"] for record in insiders) if complete else None
            ),
            "insider_ownership_percent": None,
            "ownership_display_note": None,
            "as_of_date": as_of_date,
            "calculation_method": (
                "calculated_from_individuals" if complete else "unavailable"
            ),
            "source_url": filing["source_url"] if complete else None,
        }
    return holders, summary


def parse_major_holder_text(
    text: str,
    filing: dict[str, str],
) -> list[dict[str, Any]]:
    plain = _clean_text(re.sub(r"<[^>]+>", " ", text))
    name_match = re.search(
        r"(?:name of reporting person|name of beneficial owner)\s*[:\-]?\s*"
        r"(.{2,160}?)\s+(?:check the appropriate box|aggregate amount|amount "
        r"beneficially owned)",
        plain,
        re.IGNORECASE,
    )
    shares_match = re.search(
        r"(?:aggregate amount beneficially owned|amount beneficially owned)"
        r"\s*[:\-]?\s*([\d,]+)",
        plain,
        re.IGNORECASE,
    )
    percent_match = re.search(
        r"(?:percent of class represented|percentage of class|percent of class)"
        r"\s*[:\-]?\s*(<\s*1\s*%|less than 1\s*%|\*|[\d.]+\s*%)",
        plain,
        re.IGNORECASE,
    )
    if not name_match or (not shares_match and not percent_match):
        return []
    name = _normalize_holder_name(name_match.group(1))
    percent_value, display_note = _parse_percent(
        percent_match.group(1) if percent_match else None
    )
    return [
        {
            "holder_name": name,
            "shares_held": _parse_shares(
                shares_match.group(1) if shares_match else None
            ),
            "ownership_percent": percent_value,
            "ownership_display_note": display_note,
            "holder_type": _holder_type(name),
            "as_of_date": _extract_as_of_date(plain) or filing.get("report_date"),
            "filing_type": filing["form"],
            "filing_date": filing["filing_date"],
            "accession_number": filing["accession"],
            "source_url": filing["source_url"],
        }
    ]


def select_major_filings(submissions: dict[str, Any]) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    fields = {
        name: recent.get(name) or []
        for name in (
            "form",
            "accessionNumber",
            "primaryDocument",
            "reportDate",
            "filingDate",
        )
    }
    candidates: list[dict[str, str]] = []
    for index, form in enumerate(fields["form"]):
        if form not in MAJOR_FORMS:
            continue
        accession = (
            fields["accessionNumber"][index]
            if index < len(fields["accessionNumber"])
            else ""
        )
        document = (
            fields["primaryDocument"][index]
            if index < len(fields["primaryDocument"])
            else ""
        )
        if not accession or not document:
            continue
        candidates.append(
            {
                "form": form,
                "accession": accession,
                "document": document,
                "report_date": (
                    fields["reportDate"][index]
                    if index < len(fields["reportDate"])
                    else ""
                ),
                "filing_date": (
                    fields["filingDate"][index]
                    if index < len(fields["filingDate"])
                    else ""
                ),
            }
        )

    proxies = [item for item in candidates if item["form"] == "DEF 14A"]
    if proxies:
        return sorted(proxies, key=lambda item: item["filing_date"], reverse=True)[:1]

    by_event: dict[tuple[str, str], dict[str, str]] = {}
    for item in candidates:
        base_form = item["form"].replace("/A", "")
        event_key = (base_form, item["report_date"] or item["filing_date"])
        existing = by_event.get(event_key)
        if existing is None or item["filing_date"] > existing["filing_date"]:
            by_event[event_key] = item
    return sorted(
        by_event.values(),
        key=lambda item: item["filing_date"],
        reverse=True,
    )[:5]


def _xml_text(node: ET.Element, path: str) -> str | None:
    current = node
    for part in path.split("/"):
        child = next(
            (
                item
                for item in current
                if item.tag.rsplit("}", 1)[-1] == part
            ),
            None,
        )
        if child is None:
            return None
        current = child
    return _clean_text(current.text) or None


def _xml_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def parse_ownership_xml(
    xml: str,
    filing: dict[str, str],
) -> list[dict[str, Any]]:
    root = ET.fromstring(xml)
    owners = [
        node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "reportingOwner"
    ]
    owner_rows: list[dict[str, Any]] = []
    for owner in owners:
        owner_rows.append(
            {
                "owner_name": _xml_text(owner, "reportingOwnerId/rptOwnerName")
                or "Unknown insider",
                "owner_cik": _xml_text(owner, "reportingOwnerId/rptOwnerCik"),
                "relationship": {
                    "is_director": _xml_bool(
                        _xml_text(owner, "reportingOwnerRelationship/isDirector")
                    ),
                    "is_officer": _xml_bool(
                        _xml_text(owner, "reportingOwnerRelationship/isOfficer")
                    ),
                    "is_ten_percent_owner": _xml_bool(
                        _xml_text(
                            owner,
                            "reportingOwnerRelationship/isTenPercentOwner",
                        )
                    ),
                    "is_other": _xml_bool(
                        _xml_text(owner, "reportingOwnerRelationship/isOther")
                    ),
                    "officer_title": _xml_text(
                        owner,
                        "reportingOwnerRelationship/officerTitle",
                    ),
                },
            }
        )
    if not owner_rows:
        owner_rows = [
            {
                "owner_name": "Unknown insider",
                "owner_cik": None,
                "relationship": {
                    "is_director": False,
                    "is_officer": False,
                    "is_ten_percent_owner": False,
                    "is_other": False,
                    "officer_title": None,
                },
            }
        ]

    transactions: list[dict[str, Any]] = []
    for derivative, table_name, row_name in (
        (False, "nonDerivativeTable", "nonDerivativeTransaction"),
        (True, "derivativeTable", "derivativeTransaction"),
    ):
        tables = [
            node
            for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == table_name
        ]
        for table in tables:
            rows = [
                node
                for node in table
                if node.tag.rsplit("}", 1)[-1] == row_name
            ]
            for row in rows:
                code = _xml_text(row, "transactionCoding/transactionCode")
                shares = _parse_number(
                    _xml_text(row, "transactionAmounts/transactionShares/value")
                )
                price = _parse_number(
                    _xml_text(
                        row,
                        "transactionAmounts/transactionPricePerShare/value",
                    )
                )
                nature = _xml_text(
                    row,
                    "ownershipNature/directOrIndirectOwnership/value",
                )
                for owner in owner_rows:
                    transactions.append(
                        {
                            **owner,
                            "transaction_date": _xml_text(
                                row,
                                "transactionDate/value",
                            ),
                            "filing_date": filing["filing_date"],
                            "transaction_code": code,
                            "transaction_type": TRANSACTION_CODE_TYPES.get(
                                code or "",
                                "other",
                            ),
                            "security_title": _xml_text(row, "securityTitle/value"),
                            "shares_transacted": shares,
                            "price_per_share": price,
                            "transaction_value": (
                                shares * price
                                if shares is not None and price is not None
                                else None
                            ),
                            "acquired_or_disposed": _xml_text(
                                row,
                                "transactionAmounts/transactionAcquiredDisposedCode/value",
                            ),
                            "shares_owned_after": _parse_number(
                                _xml_text(
                                    row,
                                    "postTransactionAmounts/sharesOwnedFollowingTransaction/value",
                                )
                            ),
                            "ownership_nature": (
                                "direct"
                                if nature == "D"
                                else "indirect"
                                if nature == "I"
                                else "unknown"
                            ),
                            "derivative_security": derivative,
                            "accession_number": filing["accession"],
                            "source_url": filing["source_url"],
                        }
                    )
    return transactions


def convert_13f_value_to_usd(value_in_thousands: float | int | None) -> float | None:
    if value_in_thousands is None:
        return None
    return float(value_in_thousands) * 1000


def _recent_filings(
    submissions: dict[str, Any],
    accepted_forms: set[str],
    limit: int,
) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form") or []
    rows: list[dict[str, str]] = []
    for index, form in enumerate(forms):
        if form not in accepted_forms:
            continue
        def value_at(field: str) -> str:
            values = recent.get(field) or []
            return values[index] if index < len(values) else ""

        accession = value_at("accessionNumber")
        document = value_at("primaryDocument")
        filing_date = value_at("filingDate")
        report_date = value_at("reportDate")
        if not accession or not document:
            continue
        rows.append(
            {
                "form": form,
                "accession": accession,
                "document": document,
                "filing_date": filing_date,
                "report_date": report_date,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def extract_companyfacts_shares_outstanding(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    concept = (
        payload.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
    )
    rows = concept.get("units", {}).get("shares", [])
    candidates: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        if row.get("form") not in {"10-Q", "10-K", "20-F", "40-F"}:
            continue
        if row.get("start") or not row.get("end"):
            continue
        try:
            value = int(row["val"])
        except (KeyError, TypeError, ValueError):
            continue
        if value <= 0:
            continue
        key = (row["end"], value)
        candidate = {
            "value": value,
            "as_of_date": row["end"],
            "filing_date": row.get("filed"),
            "form": row.get("form"),
            "accession_number": row.get("accn"),
            "source": "sec_companyfacts",
        }
        existing = candidates.get(key)
        if existing is None or (candidate["filing_date"] or "") > (
            existing["filing_date"] or ""
        ):
            candidates[key] = candidate
    return sorted(
        candidates.values(),
        key=lambda item: (item["as_of_date"], item["filing_date"] or ""),
    )


def parse_filing_cover_shares(
    html: str,
    filing: dict[str, str],
) -> list[dict[str, Any]]:
    text = _clean_text(re.sub(r"<[^>]+>", " ", html))
    patterns = (
        r"as of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})[^.]{0,240}?"
        r"([\d,]+)\s+shares[^.]{0,100}?outstanding",
        r"([\d,]+)\s+shares[^.]{0,100}?outstanding[^.]{0,240}?"
        r"as of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    )
    candidates: list[dict[str, Any]] = []
    for index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_text = match.group(1 if index == 0 else 2)
            shares_text = match.group(2 if index == 0 else 1)
            try:
                as_of_date = datetime.strptime(
                    date_text,
                    "%B %d, %Y",
                ).date().isoformat()
                shares = int(shares_text.replace(",", ""))
            except ValueError:
                continue
            if shares <= 0:
                continue
            candidates.append(
                {
                    "value": shares,
                    "as_of_date": as_of_date,
                    "filing_date": filing.get("filing_date"),
                    "form": filing.get("form"),
                    "accession_number": filing.get("accession"),
                    "source": "sec_filing_cover",
                    "source_url": filing.get("source_url"),
                }
            )
    return candidates


class SecHoldersProvider:
    def __init__(self, user_agent: str, timeout_seconds: float = 8) -> None:
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self.timeout_seconds = timeout_seconds

    def _resolve_company(
        self,
        client: httpx.Client,
        ticker: str,
    ) -> dict[str, Any] | None:
        global _ticker_cache
        with _cache_lock:
            cached = _ticker_cache
        if cached is None or monotonic() - cached[0] >= 24 * 60 * 60:
            response = client.get(SEC_TICKERS_URL)
            response.raise_for_status()
            payload = response.json()
            with _cache_lock:
                _ticker_cache = (monotonic(), payload)
        else:
            payload = cached[1]
        aliases = _ticker_aliases(ticker)
        return next(
            (
                row
                for row in payload.values()
                if str(row.get("ticker", "")).upper() in aliases
            ),
            None,
        )

    def fetch(self, ticker: str) -> ProviderResult:
        with _cache_lock:
            cached = _holders_cache.get(ticker)
            if cached and monotonic() - cached[0] < HOLDERS_CACHE_TTL_SECONDS:
                return cached[1]

        fetched_at = _utc_now()
        warnings: list[str] = []
        sources: list[ProviderSource] = []
        major_holders: list[dict[str, Any]] = []
        insider_summary = {
            "insider_shares": None,
            "insider_ownership_percent": None,
            "ownership_display_note": None,
            "as_of_date": None,
            "calculation_method": "unavailable",
            "source_url": None,
        }
        transactions: list[dict[str, Any]] = []

        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers=self.headers,
                follow_redirects=True,
            ) as client:
                company = self._resolve_company(client, ticker)
                if company is None:
                    return ProviderResult(
                        data=None,
                        warnings=[f"SEC does not list {ticker} in its ticker mapping."],
                    )
                cik = f"{int(company['cik_str']):010d}"
                submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik)
                submissions_response = client.get(submissions_url)
                submissions_response.raise_for_status()
                submissions = submissions_response.json()
                facts_url = SEC_COMPANY_FACTS_URL.format(cik=cik)
                shares_outstanding: list[dict[str, Any]] = []
                try:
                    facts_response = client.get(facts_url)
                    facts_response.raise_for_status()
                    shares_outstanding = (
                        extract_companyfacts_shares_outstanding(
                            facts_response.json()
                        )
                    )
                except (httpx.HTTPError, ValueError):
                    warnings.append(
                        "SEC Company Facts shares outstanding were unavailable."
                    )
                sources.append(
                    ProviderSource(
                        provider="SEC EDGAR Submissions",
                        source_url=submissions_url,
                        source_timestamp=None,
                        fetched_at=fetched_at,
                    )
                )
                sources.append(
                    ProviderSource(
                        provider="SEC EDGAR Company Facts",
                        source_url=facts_url,
                        source_timestamp=None,
                        fetched_at=fetched_at,
                    )
                )

                if not shares_outstanding:
                    for filing in _recent_filings(
                        submissions,
                        {"10-Q", "10-K", "20-F", "40-F"},
                        6,
                    ):
                        source_url = SEC_FILING_URL.format(
                            cik=int(cik),
                            accession=filing["accession"].replace("-", ""),
                            document=filing["document"],
                        )
                        try:
                            response = client.get(source_url)
                            response.raise_for_status()
                        except httpx.HTTPError:
                            continue
                        shares_outstanding.extend(
                            parse_filing_cover_shares(
                                response.text,
                                {**filing, "source_url": source_url},
                            )
                        )

                for filing in select_major_filings(submissions):
                    source_url = SEC_FILING_URL.format(
                        cik=int(cik),
                        accession=filing["accession"].replace("-", ""),
                        document=filing["document"],
                    )
                    enriched = {**filing, "source_url": source_url}
                    try:
                        response = client.get(source_url)
                        response.raise_for_status()
                        parsed, summary = parse_major_holders_html(
                            response.text,
                            enriched,
                        )
                        if not parsed and filing["form"] != "DEF 14A":
                            parsed = parse_major_holder_text(
                                response.text,
                                enriched,
                            )
                    except (httpx.HTTPError, ValueError) as exc:
                        warnings.append(
                            f"SEC {filing['form']} parsing failed for "
                            f"{filing['accession']}: {exc.__class__.__name__}."
                        )
                        continue
                    sources.append(
                        ProviderSource(
                            provider=f"SEC EDGAR {filing['form']}",
                            source_url=source_url,
                            source_timestamp=filing["filing_date"] or None,
                            fetched_at=fetched_at,
                        )
                    )
                    if parsed:
                        major_holders = parsed
                        insider_summary = summary
                        break

                for filing in _recent_filings(submissions, INSIDER_FORMS, 40):
                    raw_document = filing["document"].rsplit("/", 1)[-1]
                    source_url = SEC_FILING_URL.format(
                        cik=int(cik),
                        accession=filing["accession"].replace("-", ""),
                        document=raw_document,
                    )
                    enriched = {**filing, "source_url": source_url}
                    try:
                        response = client.get(source_url)
                        response.raise_for_status()
                        parsed = parse_ownership_xml(response.text, enriched)
                    except (httpx.HTTPError, ET.ParseError, ValueError):
                        warnings.append(
                            f"SEC ownership XML was unavailable or malformed for "
                            f"{filing['accession']}."
                        )
                        continue
                    transactions.extend(parsed)
                    sources.append(
                        ProviderSource(
                            provider=f"SEC EDGAR Form {filing['form']}",
                            source_url=source_url,
                            source_timestamp=filing["filing_date"] or None,
                            fetched_at=fetched_at,
                        )
                    )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return ProviderResult(
                data=None,
                warnings=[f"SEC holders request failed: {exc.__class__.__name__}."],
            )

        deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
        for transaction in transactions:
            key = (
                transaction["accession_number"],
                transaction["owner_name"].lower(),
                transaction["transaction_date"],
                transaction["security_title"],
                transaction["transaction_code"],
                transaction["shares_transacted"],
                transaction["price_per_share"],
                transaction["derivative_security"],
            )
            deduplicated[key] = transaction
        transactions = sorted(
            deduplicated.values(),
            key=lambda item: (
                item["transaction_date"] or "",
                item["filing_date"],
            ),
            reverse=True,
        )
        latest_dates = [
            value
            for value in (
                insider_summary["as_of_date"],
                transactions[0]["filing_date"] if transactions else None,
            )
            if value
        ]
        result = ProviderResult(
            data={
                "cik": cik,
                "company_name": submissions.get("name") or company.get("title"),
                "listed_tickers": submissions.get("tickers") or [ticker],
                "shares_outstanding_candidates": shares_outstanding,
                "major_holders": major_holders,
                "insider_ownership": insider_summary,
                "insider_transactions": transactions,
                "as_of": max(latest_dates, default=None),
            },
            sources=sources,
            warnings=warnings,
        )
        with _cache_lock:
            _holders_cache[ticker] = (monotonic(), result)
        return result
