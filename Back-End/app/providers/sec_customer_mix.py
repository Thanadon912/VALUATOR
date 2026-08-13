from __future__ import annotations

import re
from typing import Any

from app.providers.sec_supply_chain import (
    ANNUAL_FORMS,
    COUNTRIES,
    ORGANIZATION_NAME,
    _FilingTextParser,
    _normalize_text,
    _sentences,
)
from app.providers.sec_customer_mix_cache import CUSTOMER_MIX_EXTRACTOR_VERSION


SECTION_PATTERNS = (
    ("major_customers", re.compile(r"\bmajor customers?\b", re.I)),
    ("customers", re.compile(r"\bcustomers?\b", re.I)),
    (
        "concentration_of_credit_risk",
        re.compile(r"\bconcentration(?:s)? of credit risk\b", re.I),
    ),
    ("revenue_recognition", re.compile(r"\brevenue recognition\b", re.I)),
    ("segment_information", re.compile(r"\bsegment information\b", re.I)),
    (
        "notes_to_financial_statements",
        re.compile(r"\bnotes? to (?:the )?(?:consolidated )?financial statements\b", re.I),
    ),
    ("risk_factors", re.compile(r"\brisk factors?\b", re.I)),
    (
        "management_discussion_and_analysis",
        re.compile(
            r"\bmanagement(?:'s|’s)? discussion and analysis\b|\bmd&a\b",
            re.I,
        ),
    ),
    ("business", re.compile(r"\bbusiness\b", re.I)),
)

CUSTOMER_MIX_TERMS = re.compile(
    r"\b("
    r"major customers?|largest customers?|customer concentration|"
    r"concentration of credit risk|accounted for|represented|comprised|"
    r"attributable to|government customers?|public sector entities|"
    r"enterprise customers?|consumer customers?|"
    r"cloud service providers?|hyperscalers?|distributors?|resellers?|"
    r"channel partners?|end markets?|end customers?|vertical markets?|"
    r"industries served|customer base"
    r")\b",
    re.I,
)

PERCENT_VALUE = r"\d{1,3}(?:\.\d+)?"
CUSTOMER_COUNT_WORDS = {
    "one": 1,
    "a single": 1,
    "another": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

CUSTOMER_TYPE_PATTERNS = (
    ("manufacturer_customer", re.compile(
        r"\b(?:other|product)\s+manufacturers?\b",
        re.I,
    )),
    ("data_center_customer", re.compile(
        r"\bdata center customers?\b",
        re.I,
    )),
    ("industrial_customer", re.compile(
        r"\bindustrial customers?\b|\bindustrial users?\b",
        re.I,
    )),
    ("fabless_semiconductor_company", re.compile(
        r"\bfabless\s+(?:semiconductor|IC design)\s+compan(?:y|ies)\b",
        re.I,
    )),
    ("system_company", re.compile(
        r"\bsystem compan(?:y|ies)\b",
        re.I,
    )),
    ("integrated_device_manufacturer", re.compile(
        r"\bintegrated device manufacturers?\b|\bIDMs?\b",
        re.I,
    )),
    ("government", re.compile(
        r"\b(?:government customers?|public sector (?:customers?|entities|"
        r"organizations?)|(?:customers? include|serve|serves|served)"
        r"[^.;]{0,120}government agencies)\b",
        re.I,
    )),
    ("enterprise", re.compile(
        r"\b(?:enterprise customers?|commercial customers?|business customers?|"
        r"enterprises?)\b",
        re.I,
    )),
    ("consumer", re.compile(
        r"\b(?:consumer customers?|retail consumers?|individual customers?|"
        r"consumers?)\b",
        re.I,
    )),
    ("other_explicit_type", re.compile(
        r"\bsmall and mid-sized business(?:es)?\b",
        re.I,
    )),
    ("other_explicit_type", re.compile(
        r"\beducation\b",
        re.I,
    )),
    ("cloud_service_provider", re.compile(
        r"\b(?:cloud service providers?|cloud customers?|"
        r"customers? include[^.;]{0,100}(?:cloud providers?|hyperscalers?))\b",
        re.I,
    )),
    ("financial_institution", re.compile(
        r"\b(?:financial institution customers?|banking customers?|"
        r"customers? include[^.;]{0,100}(?:banks?|insurance companies?))\b",
        re.I,
    )),
    ("healthcare", re.compile(
        r"\b(?:healthcare customers?|life sciences customers?|"
        r"customers? include[^.;]{0,100}(?:hospitals?|health systems?))\b",
        re.I,
    )),
)

CHANNEL_PATTERNS = (
    ("distributor", re.compile(r"\bdistributors?\b", re.I)),
    ("reseller", re.compile(r"\bresellers?\b", re.I)),
    ("channel_partner", re.compile(r"\bchannel partners?\b", re.I)),
    ("dealer", re.compile(r"\bdealers?\b", re.I)),
    ("wholesaler", re.compile(r"\bwholesalers?\b", re.I)),
)

END_MARKET_PATTERNS = (
    ("government", re.compile(r"\b(?:government|public sector)\b", re.I)),
    ("aerospace_and_defense", re.compile(r"\b(?:aerospace|defense)\b", re.I)),
    ("automotive", re.compile(r"\b(?:automotive|automobile|vehicles?)\b", re.I)),
    ("cloud_and_data_center", re.compile(
        r"\b(?:cloud computing|cloud service providers?|data centers?|hyperscalers?)\b",
        re.I,
    )),
    ("consumer", re.compile(r"\b(?:consumer|personal computing|gaming)\b", re.I)),
    ("education", re.compile(r"\beducation(?:al)?\b", re.I)),
    ("energy", re.compile(r"\b(?:energy|oil and gas|utilities)\b", re.I)),
    ("financial_services", re.compile(
        r"\b(?:financial services|banking|insurance|capital markets)\b",
        re.I,
    )),
    ("healthcare_and_life_sciences", re.compile(
        r"\b(?:healthcare|life sciences|medical|pharmaceutical)\b",
        re.I,
    )),
    ("industrial_and_manufacturing", re.compile(
        r"\b(?:industrial|manufacturing|factory automation)\b",
        re.I,
    )),
    ("retail_and_ecommerce", re.compile(r"\b(?:retail|e-commerce|ecommerce)\b", re.I)),
    ("telecommunications", re.compile(
        r"\b(?:telecommunications|telecom|communications service providers?)\b",
        re.I,
    )),
    ("transportation_and_logistics", re.compile(
        r"\b(?:transportation|logistics|freight)\b",
        re.I,
    )),
)

AI_CANDIDATE_TERMS = re.compile(
    r"\b("
    r"customers?|customer profile|customer base|largest customer|"
    r"major customer|net revenue|net sales|accounts? receivable|"
    r"distributors?|resellers?|channel partners?|end markets?|"
    r"applications?|industries served|public sector|enterprises?|"
    r"cloud service providers?"
    r")\b",
    re.I,
)


def _section_name(text: str) -> str | None:
    looks_like_heading = (
        len(text) <= 180
        and len(text.split()) <= 20
        and not re.search(r"[.;!?]$", text)
    )
    if not looks_like_heading:
        return None
    for section, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            return section
    return None


def _percentage(value: str | None) -> float | None:
    if value is None:
        return None
    percentage = float(value)
    return percentage if 0 <= percentage <= 100 else None


def _percentage_basis(evidence: str) -> str:
    lowered = evidence.lower()
    if re.search(r"\b(accounts? receivable|receivables?)\b", lowered):
        return "accounts_receivable"
    if re.search(r"\b(revenue|revenues|net sales|sales)\b", lowered):
        return "revenue"
    return "not_specified"


def _exposure(evidence: str, percentage: float | None) -> str:
    lowered = evidence.lower()
    if percentage is not None:
        if percentage >= 50:
            return "high"
        if percentage >= 10:
            return "medium"
        return "low"
    if re.search(
        r"\b(substantially all|majority|predominantly|primarily|largest portion)\b",
        lowered,
    ):
        return "high"
    if re.search(
        r"\b(significant|substantial|material|meaningful|concentrated)\b",
        lowered,
    ):
        return "medium"
    return "not_quantified"


def _confidence(evidence: str, percentage: float | None) -> float:
    lowered = evidence.lower()
    if percentage is not None and re.search(
        r"\b(accounted for|represented|comprised|attributable to|constituted)\b",
        lowered,
    ):
        return 0.97
    if re.search(
        r"\b(depend|rely|concentrat|major customer|largest customer|"
        r"substantially all|majority|primarily)\w*\b",
        lowered,
    ):
        return 0.9
    return 0.82


def _source_fields(
    filing: dict[str, str],
    section: str | None,
    evidence: str,
    percentage: float | None = None,
) -> dict[str, Any]:
    return {
        "confidence": _confidence(evidence, percentage),
        "evidence": evidence,
        "section": section,
        "source_form": filing["form"],
        "source_accession": filing["accession"],
        "source_url": filing["source_url"],
        "filing_date": filing.get("filing_date") or None,
        "report_date": filing.get("report_date") or None,
    }


def _clean_customer_name(value: str) -> str | None:
    name = _normalize_text(value).strip(" \t\n\r,.;:()[]\"'“”")
    if re.fullmatch(
        r"(?:one|another|a single|our largest|the largest|a major|our major)"
        r"(?: direct)? customer",
        name,
        re.I,
    ):
        return None
    if re.fullmatch(r"customer\s+[A-Z0-9]+", name, re.I):
        return name
    if (
        not name[:1].isupper()
        or name in COUNTRIES
        or len(name.split()) > 8
        or re.search(
            r"\b(sales to|revenue from|customers? headquartered|"
            r"outside of|inside of|direct customers?)\b",
            name,
            re.I,
        )
    ):
        return None
    return name or None


def _customer_count(value: str | None) -> int | None:
    if not value:
        return None
    return CUSTOMER_COUNT_WORDS.get(value.lower())


def _major_customer_item(
    *,
    name: str | None,
    percentage: float | None,
    basis: str,
    customer_count: int | None,
    filing: dict[str, str],
    section: str | None,
    evidence: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "customer_count": customer_count,
        "revenue_percentage": percentage if basis == "revenue" else None,
        "percentage": percentage,
        "percentage_basis": basis,
        **_source_fields(filing, section, evidence, percentage),
    }


def _major_customers(
    evidence: str,
    filing: dict[str, str],
    section: str | None,
) -> list[dict[str, Any]]:
    if _negated_customer_threshold(evidence):
        return []
    items: list[dict[str, Any]] = []
    basis = _percentage_basis(evidence)

    explicit_label = re.compile(
        rf"\b(?P<name>Customer\s+[A-Z0-9]+|{ORGANIZATION_NAME})\s+"
        r"(?i:accounted for|represented|comprised|constituted)\s+"
        rf"(?:approximately|about|nearly|more than|less than)?\s*"
        rf"(?P<percentage>{PERCENT_VALUE})\s*%",
    )
    for match in explicit_label.finditer(evidence):
        name = _clean_customer_name(match.group("name"))
        if name is None:
            continue
        percentage = _percentage(match.group("percentage"))
        items.append(
            _major_customer_item(
                name=name,
                percentage=percentage,
                basis=basis,
                customer_count=1,
                filing=filing,
                section=section,
                evidence=evidence,
            )
        )

    anonymous = re.compile(
        r"\b(?:sales to\s+)?"
        r"(?P<count>one|another|a single|two|three|four|five)\s+"
        r"(?P<direct>direct\s+)?customers?\s+"
        r"(?P<each>each\s+)?"
        r"(?:accounted for|represented|comprised|constituted)\s+"
        r"(?P<percentages>"
        rf"{PERCENT_VALUE}\s*%"
        rf"(?:\s*(?:,\s*(?:and\s+)?|\s+and\s+)"
        rf"{PERCENT_VALUE}\s*%){{0,4}}"
        r")",
        re.I,
    )
    for match in anonymous.finditer(evidence):
        percentages = [
            _percentage(value)
            for value in re.findall(PERCENT_VALUE, match.group("percentages"))
        ]
        count = _customer_count(match.group("count"))
        if match.group("each") or len(percentages) == 1:
            items.append(
                _major_customer_item(
                    name=None,
                    percentage=percentages[0],
                    basis=basis,
                    customer_count=count,
                    filing=filing,
                    section=section,
                    evidence=evidence,
                )
            )
            continue
        for percentage in percentages:
            items.append(
                _major_customer_item(
                    name=None,
                    percentage=percentage,
                    basis=basis,
                    customer_count=1,
                    filing=filing,
                    section=section,
                    evidence=evidence,
                )
            )

    singular_anonymous = re.compile(
        r"\b(?:sales to\s+)?"
        r"(?P<label>one|another|a single|our largest|the largest|a major|our major)"
        r"\s+(?:direct\s+)?customer\s+"
        r"(?:accounted for|represented|comprised|constituted)\s+"
        rf"(?:approximately|about|nearly|more than|less than)?\s*"
        rf"(?P<percentage>{PERCENT_VALUE})\s*%",
        re.I,
    )
    for match in singular_anonymous.finditer(evidence):
        items.append(
            _major_customer_item(
                name=None,
                percentage=_percentage(match.group("percentage")),
                basis=basis,
                customer_count=1,
                filing=filing,
                section=section,
                evidence=evidence,
            )
        )

    named_without_percentage = (
        re.compile(
            rf"(?P<name>Customer\s+[A-Z0-9]+|{ORGANIZATION_NAME})\s+"
            r"(?i:is|was|remains?)\s+(?i:one of\s+)?"
            r"(?i:our\s+|the company(?:'s|’s)\s+)"
            r"(?i:largest|major|significant|principal)\s+(?i:customers?)\b",
        ),
        re.compile(
            r"\b(?i:largest|major|significant|principal)\s+(?i:customers?)\s+"
            rf"(?i:include|included)\s+(?P<name>Customer\s+[A-Z0-9]+|{ORGANIZATION_NAME})"
            r"(?=[,.;]|\s+and\b)",
        ),
    )
    for pattern in named_without_percentage:
        for match in pattern.finditer(evidence):
            name = _clean_customer_name(match.group("name"))
            if name is None:
                continue
            items.append(
                {
                    "name": name,
                    "customer_count": 1,
                    "revenue_percentage": None,
                    "percentage": None,
                    "percentage_basis": "not_specified",
                    **_source_fields(filing, section, evidence),
                }
            )
    return items


def _negated_customer_threshold(evidence: str) -> bool:
    return bool(re.search(
        r"\b(?:no|none of|not any)\b[^.;]{0,140}\bcustomers?\b"
        r"[^.;]{0,140}(?:\b(?:accounted for|represented|comprised|"
        r"constituted|exceeded|more than)\b|\d{1,3}(?:\.\d+)?\s*%)",
        evidence,
        re.I,
    ))


def _customer_type_context(evidence: str, customer_type: str) -> bool:
    lowered = evidence.lower()
    if _negated_customer_threshold(evidence):
        return False
    if customer_type == "government" and not re.search(
        r"\b(government|public sector)\b",
        lowered,
    ):
        return False
    if customer_type == "consumer" and not re.search(
        r"\b(consumer|individual customer|retail consumer)\w*\b",
        lowered,
    ):
        return False
    # A type must describe who buys/uses the company's products or services.
    # Bare mentions in product names, revenue movements, competition, or
    # macro-risk language are not customer-base disclosures.
    explicit_type_label = bool(re.search(
        r"\b(?:government|public sector|enterprise|commercial|business|"
        r"consumer|individual|data center|industrial|healthcare|"
        r"life sciences|financial institution|banking|cloud)\s+customers?\b",
        lowered,
    ))
    if explicit_type_label:
        return True
    return bool(re.search(
        r"\b(?:customers?\s+(?:include|are|comprise|consist of)|"
        r"customer base\s+(?:includes?|comprises?|consists of)|"
        r"count among our customers|"
        r"(?:serve|serves|served|sell|sells|sold|sales to|provide(?:s|d)? "
        r"services to)\b[^.;]{0,160}|"
        r"\b(?:purchase|purchases|use|uses)\s+(?:our|the company's)\b)",
        lowered,
    ))


def _customer_type_label(customer_type: str, label: str) -> str:
    if (
        customer_type == "other_explicit_type"
        and re.fullmatch(
            r"small and mid-sized business(?:es)?",
            label,
            re.I,
        )
    ):
        return "small and mid-sized businesses"
    return label


def _channel_dependency_context(evidence: str) -> bool:
    return bool(re.search(
        r"\b(depend(?:s|ed|ence|ent)?(?: substantially| primarily)? on|"
        r"rely|reliance|(?:significant|substantial|majority) (?:amount|portion)"
        r" of (?:our )?(?:revenue|sales)[^.;]{0,100}(?:through|from)|"
        r"(?:revenue|sales)[^.;]{0,100}(?:through|from)|"
        r"sales through|sell through|limited number of)\b",
        evidence,
        re.I,
    ))


def _explicit_end_market_context(evidence: str) -> bool:
    return bool(re.search(
        r"\b(end markets?|vertical markets?|industries served|"
        r"customer industries|industries in which (?:our )?customers? "
        r"operate|markets? (?:we|the company) serve)\b|"
        r"\bcustomer base\b[^.;]{0,180}\bmarkets?\b|"
        r"\b(?:we|the company) serve\b[^.;]{0,180}\bmarkets?\b|"
        r"\b(?:battery|electric vehicle|automotive|aerospace|defense|"
        r"healthcare|industrial|telecommunications|energy|financial services)"
        r" markets?\b|"
        r"\b(?:customer profile|customers?' business|customer concentration)"
        r"[^.;]{0,260}\b(?:applications?|markets?|industries)\b",
        evidence,
        re.I,
    ))


def _end_market_supported(market: str, evidence: str) -> bool:
    lowered = evidence.lower()
    if market == "government":
        return bool(re.search(
            r"\b(government markets?|government customers?|"
            r"public sector(?: markets?| customers?| entities)?)\b",
            lowered,
        ))
    if market == "consumer":
        return bool(re.search(
            r"\b(consumer markets?|consumer customers?|"
            r"retail consumers?|personal computing|gaming)\b",
            lowered,
        ))
    return True


def _channel_name(evidence: str, channel_type: str) -> str | None:
    singular = {
        "distributor": "distributor",
        "reseller": "reseller",
        "channel_partner": "channel partner",
        "dealer": "dealer",
        "wholesaler": "wholesaler",
    }[channel_type]
    patterns = (
        re.compile(
            rf"\b(?P<name>{ORGANIZATION_NAME})\s+(?:is|was|serves? as)\s+"
            rf"(?:our\s+)?(?:primary|principal|largest|major|exclusive)?\s*"
            rf"{re.escape(singular)}\b"
        ),
        re.compile(
            rf"\b(?:rely|depend)\s+(?:primarily\s+|substantially\s+)?on\s+"
            rf"(?P<name>{ORGANIZATION_NAME})\s+(?:as|for)\s+"
            rf"(?:our\s+)?{re.escape(singular)}\b",
            re.I,
        ),
    )
    for pattern in patterns:
        match = pattern.search(evidence)
        if match:
            return _clean_customer_name(match.group("name"))
    return None


def _risk_types(evidence: str) -> list[str]:
    lowered = evidence.lower()
    risks: list[str] = []
    if (
        not _negated_customer_threshold(evidence)
        and
        not re.search(
            r"\bcustomers? headquartered\b|\bcustomers? located\b",
            lowered,
        )
        and re.search(
            r"\b(customer concentration[^.;]{0,150}(?:revenue|sales)|"
            r"(?:revenue|sales)[^.;]{0,150}customer concentration|"
            r"revenue (?:is |was )?concentrated|"
            r"concentration of (?:our )?(?:revenue|sales)|"
            r"largest customer|major customer|"
            r"(?:direct\s+)?customers?\s+(?:accounted for|represented)"
            r"[^.;]{0,100}\b(?:revenue|sales)\b|"
            r"(?:one|another|two|three|four|five)\s+(?:direct\s+)?"
            r"customers?[^.;]{0,100}\b(?:revenue|sales)\b|"
            r"limited number of customers[^.;]{0,100}\b(?:revenue|sales)\b|"
            r"loss of [^.;]{0,40}customers?[^.;]{0,100}\b(?:revenue|sales)\b)",
            lowered,
        )
    ):
        risks.append("customer_concentration")
    if _customer_type_context(evidence, "government") and re.search(
        r"\b(depend|rely|concentrat|accounted for|represented)\w*\b",
        lowered,
    ):
        risks.append("government_customer_dependency")
    if re.search(r"\b(distributor|reseller|channel partner|dealer|wholesaler)s?\b", lowered):
        if _channel_dependency_context(evidence):
            risks.append("channel_partner_dependency")
    if re.search(r"\b(end markets?|vertical markets?)\b", lowered) and re.search(
        r"\b(concentrat|depend|rely|substantial|significant|majority)\w*\b",
        lowered,
    ):
        risks.append("end_market_concentration")
    return risks


def _severity(evidence: str, percentage: float | None) -> str:
    lowered = evidence.lower()
    if percentage is not None and percentage >= 20:
        return "high"
    if re.search(
        r"\b(substantially all|majority|material adverse|largest customer)\b",
        lowered,
    ):
        return "high"
    if percentage is not None and percentage >= 10:
        return "medium"
    if re.search(
        r"\b(significant|substantial|concentrated|depend|rely)\w*\b",
        lowered,
    ):
        return "medium"
    return "unknown"


def _dedupe_best(
    items: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        key = tuple(
            value.casefold().strip() if isinstance(value, str) else value
            for value in (item.get(field) for field in keys)
        )
        existing = selected.get(key)
        rank = (
            {"high": 3, "medium": 2, "low": 1, "unknown": 0}.get(
                item.get("severity"),
                0,
            ),
            1 if item.get("percentage_basis") == "revenue" else 0,
            item.get("confidence", 0),
            item.get("filing_date") or "",
            -len(item.get("evidence") or ""),
        )
        existing_rank = (
            {"high": 3, "medium": 2, "low": 1, "unknown": 0}.get(
                existing.get("severity"),
                0,
            ),
            1 if existing.get("percentage_basis") == "revenue" else 0,
            existing.get("confidence", 0),
            existing.get("filing_date") or "",
            -len(existing.get("evidence") or ""),
        ) if existing else (-1, -1, -1, "", 0)
        if existing is None or rank > existing_rank:
            selected[key] = item
    return list(selected.values())


def collect_customer_mix_passages(
    filings: list[dict[str, str]],
    limit_per_filing: int = 24,
) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    for filing in filings:
        parser = _FilingTextParser()
        parser.feed(filing["html"])
        parser.close()
        sections: list[str | None] = []
        section: str | None = None
        anchors: list[int] = []

        for index, block in enumerate(parser.blocks):
            detected_section = _section_name(block)
            if detected_section:
                section = detected_section
            sections.append(section)
            if AI_CANDIDATE_TERMS.search(block):
                anchors.append(index)

        intervals: list[list[int]] = []
        for anchor in anchors:
            start = max(0, anchor - 3)
            end = min(len(parser.blocks), anchor + 5)
            if (
                intervals
                and start <= intervals[-1][1]
                and end - intervals[-1][0] <= 12
            ):
                intervals[-1][1] = max(intervals[-1][1], end)
            else:
                intervals.append([start, end])

        filing_passages: list[dict[str, Any]] = []
        for start, end in intervals:
            window_blocks = parser.blocks[start:end]
            text = _normalize_text(" ".join(window_blocks))
            if len(text) < 45:
                continue
            if len(text) > 4_000:
                text = text[:4_000].rsplit(" ", 1)[0]
            score = len(re.findall(
                r"\b(customer|revenue|sales|receivable|distributor|"
                r"reseller|end market|enterprise|public sector)\w*\b",
                text,
                re.I,
            ))
            score += 5 * len(re.findall(
                r"\b\d{1,3}(?:\.\d+)?\s*%",
                text,
            ))
            if re.search(
                r"\b(count among our customers|customers?\s*,?\s+including|"
                r"customers? include|ranging from)\b",
                text,
                re.I,
            ):
                score += 30
            if re.search(
                r"\b(fabless|system companies|integrated device manufacturer|"
                r"enterprise customers?|government customers?|"
                r"cloud service providers?)\b",
                text,
                re.I,
            ):
                score += 20
            filing_passages.append(
                {
                    "passage_id": (
                        f"{filing['accession']}:customer-mix:"
                        f"{len(filing_passages)}"
                    ),
                    "section": sections[min(start, len(sections) - 1)],
                    "evidence": text,
                    "score": score,
                    "filing": filing,
                }
            )

        passages.extend(
            sorted(
                filing_passages,
                key=lambda item: (-item["score"], item["passage_id"]),
            )[:limit_per_filing]
        )
    return passages


def extract_customer_mix(
    ticker: str,
    filings: list[dict[str, str]],
) -> dict[str, Any]:
    major_customers: list[dict[str, Any]] = []
    customer_types: list[dict[str, Any]] = []
    channel_dependencies: list[dict[str, Any]] = []
    end_markets: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []

    for filing in filings:
        parser = _FilingTextParser()
        parser.feed(filing["html"])
        parser.close()
        section: str | None = None

        for block in parser.blocks:
            detected_section = _section_name(block)
            if detected_section:
                section = detected_section
                if len(block) <= 180:
                    continue

            passages = _sentences(block)
            if not passages and 25 <= len(block) <= 900:
                passages = [_normalize_text(block)]

            for evidence in passages:
                if not CUSTOMER_MIX_TERMS.search(evidence):
                    continue

                percentages = [] if _negated_customer_threshold(evidence) else [
                    _percentage(value)
                    for value in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", evidence)
                ]
                percentage = percentages[0] if len(percentages) == 1 else None
                source = _source_fields(filing, section, evidence, percentage)

                major_customers.extend(
                    _major_customers(evidence, filing, section)
                )

                for customer_type, pattern in CUSTOMER_TYPE_PATTERNS:
                    matched_label = pattern.search(evidence)
                    if (
                        matched_label
                        and _customer_type_context(evidence, customer_type)
                    ):
                        customer_types.append(
                            {
                                "type": customer_type,
                                "label": _customer_type_label(
                                    customer_type,
                                    matched_label.group(0),
                                ),
                                "exposure": _exposure(evidence, percentage),
                                "revenue_percentage": (
                                    percentage
                                    if _percentage_basis(evidence) == "revenue"
                                    else None
                                ),
                                **source,
                            }
                        )

                for channel_type, pattern in CHANNEL_PATTERNS:
                    if (
                        not pattern.search(evidence)
                        or not _channel_dependency_context(evidence)
                    ):
                        continue
                    channel_dependencies.append(
                        {
                            "type": channel_type,
                            "name": _channel_name(evidence, channel_type),
                            "exposure": _exposure(evidence, percentage),
                            "revenue_percentage": (
                                percentage
                                if _percentage_basis(evidence) == "revenue"
                                else None
                            ),
                            **source,
                        }
                    )

                has_end_market_context = _explicit_end_market_context(evidence)
                if has_end_market_context:
                    for market, pattern in END_MARKET_PATTERNS:
                        if (
                            pattern.search(evidence)
                            and _end_market_supported(market, evidence)
                        ):
                            end_markets.append(
                                {
                                    "market": market,
                                    "exposure": _exposure(evidence, percentage),
                                    "revenue_percentage": (
                                        percentage
                                        if _percentage_basis(evidence) == "revenue"
                                        else None
                                    ),
                                    **source,
                                }
                            )

                for risk_type in _risk_types(evidence):
                    risk_percentage = max(
                        (value for value in percentages if value is not None),
                        default=None,
                    )
                    risks.append(
                        {
                            "type": risk_type,
                            "severity": _severity(evidence, risk_percentage),
                            "percentage": risk_percentage,
                            "percentage_basis": _percentage_basis(evidence),
                            **_source_fields(
                                filing,
                                section,
                                evidence,
                                risk_percentage,
                            ),
                        }
                    )

        for passage in collect_customer_mix_passages(
            [filing],
            limit_per_filing=32,
        ):
            passage_evidence = passage["evidence"]
            segments = _sentences(passage_evidence)
            if not segments:
                segments = [passage_evidence]
            for evidence in segments:
                for customer_type, pattern in CUSTOMER_TYPE_PATTERNS:
                    matched_label = pattern.search(evidence)
                    if (
                        matched_label
                        and _customer_type_context(evidence, customer_type)
                    ):
                        customer_types.append(
                            {
                                "type": customer_type,
                                "label": _customer_type_label(
                                    customer_type,
                                    matched_label.group(0),
                                ),
                                "exposure": _exposure(evidence, None),
                                "revenue_percentage": None,
                                **_source_fields(
                                    filing,
                                    passage["section"],
                                    evidence,
                                ),
                            }
                        )
                has_end_market_context = _explicit_end_market_context(evidence)
                if has_end_market_context:
                    for market, pattern in END_MARKET_PATTERNS:
                        if (
                            pattern.search(evidence)
                            and _end_market_supported(market, evidence)
                        ):
                            end_markets.append(
                                {
                                    "market": market,
                                    "exposure": _exposure(evidence, None),
                                    "revenue_percentage": None,
                                    **_source_fields(
                                        filing,
                                        passage["section"],
                                        evidence,
                                    ),
                                }
                            )

    annual = next(
        (filing for filing in filings if filing["form"] in ANNUAL_FORMS),
        None,
    )
    fiscal_year = None
    if annual and re.match(r"^\d{4}-\d{2}-\d{2}$", annual.get("report_date", "")):
        fiscal_year = int(annual["report_date"][:4])

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "extraction": {
            "method": "deterministic",
            "provider": None,
            "model": None,
            "extractor_version": CUSTOMER_MIX_EXTRACTOR_VERSION,
            "cache_source": None,
            "attempted_models": [],
            "model_failover_used": False,
            "model_failover_reason": None,
            "fallback_used": False,
            "fallback_reason": None,
        },
        "analyzed_filings": [
            {
                "form": filing["form"],
                "accession": filing["accession"],
                "filing_date": filing.get("filing_date") or None,
                "report_date": filing.get("report_date") or None,
                "source_url": filing["source_url"],
            }
            for filing in filings
        ],
        "customer_mix": {
            "major_customers": _dedupe_best(
                major_customers,
                (
                    "name",
                    "percentage",
                    "percentage_basis",
                    "customer_count",
                ),
            ),
            "customer_types": _dedupe_best(
                customer_types,
                ("type", "label"),
            ),
            "channel_dependencies": _dedupe_best(
                channel_dependencies,
                ("type", "name"),
            ),
            "end_markets": _dedupe_best(
                end_markets,
                ("market",),
            ),
            "risks": _dedupe_best(
                risks,
                ("type",),
            ),
        },
    }
