from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any


EXECUTIVE_FORMS_PROVIDER = "SEC DEF 14A"
LOW_CONFIDENCE_UNAVAILABLE = "DEF 14A parser confidence below threshold"


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _parse_number(value: str | None) -> float | int | None:
    text = _clean_text(value)
    if not text or text in {"-", "—", "N/A", "n/a", "*"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", ".", "-", "-."}:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    value_out = -parsed if negative and parsed > 0 else parsed
    return int(value_out) if value_out.is_integer() else value_out


class _TextAndTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.text_parts: list[str] = []
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
        elif tag in {"br", "p", "div"}:
            if self._cell is not None:
                self._cell.append(" ")
            self.text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None and self._sup_depth == 0:
            self._cell.append(data)
        if not self._table_depth:
            self.text_parts.append(data)

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


def _parse_html(html: str) -> tuple[list[list[list[str]]], str]:
    parser = _TextAndTableParser()
    parser.feed(html)
    return parser.tables, _clean_text(" ".join(parser.text_parts))


def _header_map(row: list[str]) -> dict[str, int]:
    return {_normalize_key(cell): index for index, cell in enumerate(row)}


def _cell(row: list[str], headers: dict[str, int], *keys: str) -> str | None:
    for key in keys:
        index = headers.get(key)
        if index is not None and index < len(row):
            return row[index]
    return None


def _compensation_key(headers: dict[str, int], target: str) -> str | None:
    aliases = {
        "name": ("name", "name_and_principal_position"),
        "year": ("year",),
        "salary": ("salary",),
        "bonus": ("bonus",),
        "stock_awards": ("stock_awards", "stock_award"),
        "option_awards": ("option_awards", "option_award"),
        "non_equity_incentive_plan_compensation": (
            "non_equity_incentive_plan_compensation",
            "non_equity_incentive_plan",
            "non_equity_incentive_compensation",
        ),
        "all_other_compensation": ("all_other_compensation",),
        "total_compensation": ("total", "total_compensation"),
    }
    for alias in aliases[target]:
        if alias in headers:
            return alias
    return None


def parse_summary_compensation_table(
    html: str,
    filing: dict[str, str],
) -> list[dict[str, Any]]:
    tables, _ = _parse_html(html)
    rows_out: list[dict[str, Any]] = []
    for table in tables:
        if len(table) < 2:
            continue
        headers = _header_map(table[0])
        if not (
            _compensation_key(headers, "name")
            and _compensation_key(headers, "year")
            and _compensation_key(headers, "salary")
            and _compensation_key(headers, "total_compensation")
        ):
            continue
        if not (
            _compensation_key(headers, "stock_awards")
            or _compensation_key(headers, "option_awards")
        ):
            continue
        for row in table[1:]:
            name = _cell(row, headers, _compensation_key(headers, "name") or "")
            year = _parse_number(_cell(row, headers, "year"))
            if not name or year is None:
                continue
            record = {
                "name": _clean_text(re.sub(r"\(\d+\)", "", name)),
                "year": int(year),
                "salary": _parse_number(_cell(row, headers, "salary")),
                "bonus": _parse_number(_cell(row, headers, "bonus")),
                "stock_awards": _parse_number(
                    _cell(row, headers, _compensation_key(headers, "stock_awards") or "")
                ),
                "option_awards": _parse_number(
                    _cell(row, headers, _compensation_key(headers, "option_awards") or "")
                ),
                "non_equity_incentive_plan_compensation": _parse_number(
                    _cell(
                        row,
                        headers,
                        _compensation_key(
                            headers,
                            "non_equity_incentive_plan_compensation",
                        )
                        or "",
                    )
                ),
                "all_other_compensation": _parse_number(
                    _cell(
                        row,
                        headers,
                        _compensation_key(headers, "all_other_compensation") or "",
                    )
                ),
                "total_compensation": _parse_number(
                    _cell(
                        row,
                        headers,
                        _compensation_key(headers, "total_compensation") or "",
                    )
                ),
                "provider": EXECUTIVE_FORMS_PROVIDER,
                "filing_date": filing.get("filing_date"),
                "filing_url": filing["source_url"],
                "evidence": " | ".join(row),
                "confidence": 0.9,
            }
            rows_out.append(record)
    return rows_out


def parse_key_executive_tables(
    html: str,
    filing: dict[str, str],
    compensation_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    tables, _ = _parse_html(html)
    compensation_by_name = {
        row["name"].lower(): row.get("total_compensation")
        for row in compensation_rows or []
        if row.get("name")
    }
    executives: dict[str, dict[str, Any]] = {}
    for table in tables:
        if len(table) < 2:
            continue
        headers = _header_map(table[0])
        has_name = "name" in headers or "name_and_principal_position" in headers
        has_role = any(key in headers for key in ("title", "position", "principal_position"))
        if not has_name or not has_role:
            continue
        for row in table[1:]:
            name = _cell(row, headers, "name", "name_and_principal_position")
            title = _cell(row, headers, "title", "position", "principal_position")
            if not name or not title:
                continue
            age_value = _parse_number(_cell(row, headers, "age"))
            year_born = _parse_number(_cell(row, headers, "year_born", "birth_year"))
            normalized_name = _clean_text(re.sub(r"\(\d+\)", "", name))
            executives[normalized_name.lower()] = {
                "name": normalized_name,
                "title": title,
                "role": title,
                "age": int(age_value) if age_value is not None else None,
                "year_born": int(year_born) if year_born is not None else None,
                "compensation": compensation_by_name.get(normalized_name.lower()),
                "pay": compensation_by_name.get(normalized_name.lower()),
                "provider": EXECUTIVE_FORMS_PROVIDER,
                "filing_date": filing.get("filing_date"),
                "filing_url": filing["source_url"],
                "evidence": " | ".join(row),
                "confidence": 0.86,
            }
    for row in compensation_rows or []:
        key = row["name"].lower()
        executives.setdefault(
            key,
            {
                "name": row["name"],
                "title": None,
                "role": None,
                "age": None,
                "year_born": None,
                "compensation": row.get("total_compensation"),
                "pay": row.get("total_compensation"),
                "provider": EXECUTIVE_FORMS_PROVIDER,
                "filing_date": filing.get("filing_date"),
                "filing_url": filing["source_url"],
                "evidence": row["evidence"],
                "confidence": 0.78,
            },
        )
    return list(executives.values())


def parse_governance_disclosures(
    html: str,
    filing: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    tables, text = _parse_html(html)
    directors: list[dict[str, Any]] = []
    for table in tables:
        if len(table) < 2:
            continue
        headers = _header_map(table[0])
        if "name" not in headers or "director" not in " ".join(headers):
            continue
        for row in table[1:]:
            name = _cell(row, headers, "name")
            if not name:
                continue
            directors.append(
                {
                    "name": _clean_text(name),
                    "role": _cell(row, headers, "director_since", "position"),
                    "provider": EXECUTIVE_FORMS_PROVIDER,
                    "filing_date": filing.get("filing_date"),
                    "filing_url": filing["source_url"],
                    "evidence": " | ".join(row),
                    "confidence": 0.8,
                }
            )
    committees = []
    committee_patterns = [
        "Audit Committee",
        "Compensation Committee",
        "Nominating and Corporate Governance Committee",
        "Governance Committee",
    ]
    for label in committee_patterns:
        match = re.search(rf"[^.]*\b{re.escape(label)}\b[^.]*\.", text, re.I)
        if match:
            committees.append(
                {
                    "name": label,
                    "members": [],
                    "provider": EXECUTIVE_FORMS_PROVIDER,
                    "filing_date": filing.get("filing_date"),
                    "filing_url": filing["source_url"],
                    "evidence": _clean_text(match.group(0)),
                    "confidence": 0.75,
                }
            )
    voting_matters = []
    voting_patterns = [
        ("auditor ratification", r"ratif(?:y|ication)[^.]{0,120}auditor"),
        ("say-on-pay", r"(?:say[- ]on[- ]pay|executive compensation vote|advisory vote[^.]{0,80}compensation)"),
        ("election of directors", r"election of directors"),
    ]
    for label, pattern in voting_patterns:
        match = re.search(rf"[^.]*{pattern}[^.]*\.", text, re.I)
        if match:
            voting_matters.append(
                {
                    "matter": label,
                    "provider": EXECUTIVE_FORMS_PROVIDER,
                    "filing_date": filing.get("filing_date"),
                    "filing_url": filing["source_url"],
                    "evidence": _clean_text(match.group(0)),
                    "confidence": 0.76,
                }
            )
    notes = []
    for label, pattern in (
        ("Independent director disclosure", r"independent directors?"),
        ("Board committee disclosure", r"board committees?"),
    ):
        match = re.search(rf"[^.]*{pattern}[^.]*\.", text, re.I)
        if match:
            notes.append(
                {
                    "name": label,
                    "role": None,
                    "provider": EXECUTIVE_FORMS_PROVIDER,
                    "filing_date": filing.get("filing_date"),
                    "filing_url": filing["source_url"],
                    "evidence": _clean_text(match.group(0)),
                    "confidence": 0.72,
                }
            )
    return {
        "directors": directors,
        "committees": committees,
        "voting_matters": voting_matters,
        "notes": notes,
    }


def extract_def14a_profile(html: str, filing: dict[str, str]) -> dict[str, Any]:
    compensation = parse_summary_compensation_table(html, filing)
    executives = parse_key_executive_tables(html, filing, compensation)
    governance = parse_governance_disclosures(html, filing)
    unavailable = []
    if not executives:
        unavailable.append(LOW_CONFIDENCE_UNAVAILABLE + ": key executives")
    if not compensation:
        unavailable.append(LOW_CONFIDENCE_UNAVAILABLE + ": compensation")
    if not any(governance.values()):
        unavailable.append(LOW_CONFIDENCE_UNAVAILABLE + ": governance")
    return {
        "key_executives": executives,
        "executive_compensation": compensation,
        "governance": governance,
        "unavailable": unavailable,
    }
