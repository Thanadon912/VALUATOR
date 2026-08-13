from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

from app.providers.sec_supply_chain_cache import SUPPLY_CHAIN_EXTRACTOR_VERSION


ANNUAL_FORMS = {"10-K", "20-F", "40-F"}

SECTION_PATTERNS = (
    ("risk_factors", re.compile(r"\brisk factors?\b", re.I)),
    (
        "management_discussion_and_analysis",
        re.compile(
            r"\bmanagement(?:'s|’s)? discussion and analysis\b|\bmd&a\b",
            re.I,
        ),
    ),
    ("manufacturing", re.compile(r"\bmanufactur(?:ing|ers?)\b", re.I)),
    ("supply_chain", re.compile(r"\bsupply chain\b", re.I)),
    ("suppliers", re.compile(r"\bsuppliers?\b", re.I)),
    ("properties", re.compile(r"\bproperties\b", re.I)),
    ("business", re.compile(r"\bbusiness\b", re.I)),
)

SUPPLY_TERMS = re.compile(
    r"\b("
    r"supply chain|suppliers?|vendors?|foundr(?:y|ies)|fabricat(?:e|es|ed|ion)|"
    r"manufactur(?:e|ed|er|ers|ing)|contract manufactur(?:e|ed|er|ers|ing)|"
    r"assembl(?:e|er|ers|y|ies)|raw material|component|single[- ]source|"
    r"sole[- ]source|customer concentration|largest customer|"
    r"distribution partner|logistics provider|production facilit(?:y|ies)|"
    r"subcontractor|purchas(?:e|ed|ing)|procur(?:e|ed|ing)|sourc(?:e|ed|ing)"
    r")\b",
    re.I,
)

ORGANIZATION_SUFFIX = (
    r"(?:Inc\.?|Incorporated|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|Limited|"
    r"LLC|L\.L\.C\.|PLC|plc|AG|N\.V\.|NV|S\.A\.|SE|Group|Holdings|"
    r"Semiconductor(?:s)?|Technology|Technologies|Pharmaceuticals?)"
)
ORGANIZATION_NAME = (
    rf"[A-Z][A-Za-z0-9&'’.\-]*(?:\s+[A-Z0-9][A-Za-z0-9&'’.\-]*){{0,7}}"
    rf"(?:\s+{ORGANIZATION_SUFFIX})?"
)

COUNTRIES = (
    "Argentina",
    "Australia",
    "Austria",
    "Belgium",
    "Brazil",
    "Canada",
    "Chile",
    "China",
    "Czech Republic",
    "Denmark",
    "Finland",
    "France",
    "Germany",
    "Hungary",
    "India",
    "Indonesia",
    "Ireland",
    "Israel",
    "Italy",
    "Japan",
    "Malaysia",
    "Mexico",
    "Netherlands",
    "Norway",
    "Philippines",
    "Poland",
    "Portugal",
    "Romania",
    "Singapore",
    "South Africa",
    "South Korea",
    "Spain",
    "Sweden",
    "Switzerland",
    "Taiwan",
    "Thailand",
    "Turkey",
    "United Kingdom",
    "United States",
    "Vietnam",
)

MATERIAL_TERMS = (
    "active pharmaceutical ingredients",
    "aluminum",
    "batteries",
    "battery cells",
    "chemicals",
    "cobalt",
    "components",
    "copper",
    "critical minerals",
    "glass",
    "lithium",
    "memory",
    "microprocessors",
    "natural gas",
    "nickel",
    "packaging materials",
    "paper",
    "plastics",
    "rare earth elements",
    "rare earth minerals",
    "resins",
    "semiconductors",
    "silicon wafers",
    "steel",
    "timber",
    "uranium",
)

GENERIC_NAMES = {
    "Company",
    "Customers",
    "Manufacturers",
    "Our Company",
    "Suppliers",
    "The Company",
    "Third Parties",
    "Vendors",
    "We",
}

GENERIC_MATERIAL_TERMS = {
    "component",
    "components",
    "material",
    "materials",
    "supplies",
}


class _FilingTextParser(HTMLParser):
    BLOCK_TAGS = {
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "table",
        "td",
        "th",
        "tr",
    }
    SKIP_TAGS = {"script", "style", "ix:hidden"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._parts: list[str] = []
        self._skip_depth = 0

    def _flush(self) -> None:
        text = _normalize_text(" ".join(self._parts))
        self._parts = []
        if text and (not self.blocks or self.blocks[-1] != text):
            self.blocks.append(text)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.lower()
        if lowered in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if not self._skip_depth and lowered in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if not self._skip_depth and lowered in self.BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _section_name(text: str) -> str | None:
    looks_like_heading = (
        len(text) <= 180
        and len(text.split()) <= 18
        and not re.search(r"[.;!?]$", text)
    )
    if not looks_like_heading:
        return None
    for section, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            return section
    return None


def _sentences(block: str) -> list[str]:
    return [
        sentence.strip(" •")
        for sentence in re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9])", block)
        if 45 <= len(sentence.strip()) <= 900
    ]


def _percentage(text: str) -> float | None:
    match = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    value = float(match.group(1))
    return value if 0 <= value <= 100 else None


def _clean_name(value: str) -> str | None:
    name = re.sub(
        r"^(?:our|the|a|an|certain|one of our|some of our)\s+",
        "",
        _normalize_text(value),
        flags=re.I,
    ).strip(" ,.;:()")
    name = re.sub(
        r"\s+(?:which|that|who|for|to|as|and)\s*$",
        "",
        name,
        flags=re.I,
    ).strip(" ,.;:")
    if (
        not name
        or name in GENERIC_NAMES
        or len(name.split()) > 9
        or name.lower().startswith(
            ("supplier", "manufacturer", "customer", "third party")
        )
    ):
        return None
    return name


def _confidence(evidence: str) -> float:
    lowered = evidence.lower()
    if re.search(r"\b(sole|single[- ]source|exclusively|substantially all)\b", lowered):
        return 0.98
    if re.search(
        r"\b(primary|principal|key supplier|contract manufacturer|"
        r"accounted for \d|represented \d)\b",
        lowered,
    ):
        return 0.95
    if re.search(
        r"\b(rely|depend|manufactured by|assembled by|limited number|"
        r"concentrated)\b",
        lowered,
    ):
        return 0.9
    return 0.82


def _source_fields(
    filing: dict[str, str],
    section: str | None,
    evidence: str,
) -> dict[str, Any]:
    return {
        "confidence": _confidence(evidence),
        "concentration_qualifier": _concentration_qualifier(evidence),
        "evidence": evidence,
        "section": section,
        "source_form": filing["form"],
        "source_accession": filing["accession"],
        "source_url": filing["source_url"],
        "filing_date": filing.get("filing_date") or None,
        "report_date": filing.get("report_date") or None,
    }


def _concentration_qualifier(evidence: str) -> str | None:
    lowered = evidence.lower()
    qualifiers = (
        ("substantially_all", r"\bsubstantially all\b"),
        ("significant_majority", r"\bsignificant majority\b"),
        ("majority", r"\bmajority\b"),
        ("single_source", r"\b(single[- ]source|sole[- ]source)\b"),
        ("limited_number", r"\b(limited number|few suppliers|few vendors)\b"),
        ("primary", r"\b(primary|principally|primarily)\b"),
    )
    for qualifier, pattern in qualifiers:
        if re.search(pattern, lowered):
            return qualifier
    return None


def _relationship_type(evidence: str) -> str:
    lowered = evidence.lower()
    if "contract manufactur" in lowered:
        return "contract_manufacturer"
    if "foundry" in lowered or "fabricat" in lowered:
        return "foundry"
    if "assembl" in lowered:
        return "assembly_partner"
    if "logistics" in lowered or "distribution partner" in lowered:
        return "logistics_or_distribution_partner"
    if "manufactur" in lowered or "produc" in lowered:
        return "manufacturing_partner"
    return "supplier"


def _role(evidence: str, relationship_type: str) -> str:
    lowered = evidence.lower()
    qualifiers = []
    if re.search(r"\b(sole|single[- ]source)\b", lowered):
        qualifiers.append("single-source")
    elif "primary" in lowered or "principal" in lowered:
        qualifiers.append("primary")
    elif "key " in lowered:
        qualifiers.append("key")
    labels = {
        "contract_manufacturer": "contract manufacturer",
        "foundry": "semiconductor foundry or fabrication partner",
        "assembly_partner": "assembly partner",
        "logistics_or_distribution_partner": "logistics or distribution partner",
        "manufacturing_partner": "manufacturing partner",
        "supplier": "supplier",
    }
    return " ".join([*qualifiers, labels[relationship_type]]).capitalize()


def _supplier_names(evidence: str) -> list[str]:
    patterns = (
        re.compile(
            rf"\b(?:rely|depends?|dependent)\s+(?:primarily\s+|substantially\s+)?"
            rf"on\s+({ORGANIZATION_NAME})(?=\s+(?:for|to|as|which|that)|[,.;])"
        ),
        re.compile(
            rf"\b({ORGANIZATION_NAME})\s+(?:is|are|serves? as|acts? as)\s+"
            rf"(?:our|the company(?:'s|’s)?)?\s*(?:primary|principal|sole|"
            rf"single[- ]source|key|major)?\s*(?:supplier|manufacturer|"
            rf"contract manufacturer|foundry|assembly partner)"
        ),
        re.compile(
            rf"\b(?:manufactured|fabricated|assembled|produced)\s+"
            rf"(?:primarily\s+|principally\s+|exclusively\s+)?by\s+"
            rf"({ORGANIZATION_NAME})(?=[,.;]|\s+(?:in|at|which|that))"
        ),
        re.compile(
            rf"\b(?:suppliers?|manufacturers?|contract manufacturers?|"
            rf"foundries|assembly partners)\s+(?:include|including)\s+"
            rf"({ORGANIZATION_NAME})(?=[,.;]|\s+and\b)"
        ),
    )
    names: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(evidence):
            name = _clean_name(match.group(1))
            if name and name not in names:
                names.append(name)
    return names


def _risk_types(evidence: str) -> list[str]:
    lowered = evidence.lower()
    types: list[str] = []
    if re.search(r"\b(single[- ]source|sole[- ]source|only source)\b", lowered):
        types.append("single_source_dependency")
    if (
        re.search(
            r"\b(limited number of|few suppliers|supplier concentration|"
            r"concentrated among|substantial portion)\b",
            lowered,
        )
        and re.search(
            r"\b(suppliers?|vendors?|manufacturers?|foundr(?:y|ies))\b",
            lowered,
        )
        and not re.search(r"\b(receivables?|accounts? payable)\b", lowered)
        and re.search(
            r"\b(supply|source|manufactur|procur|depend|rely)\w*\b",
            lowered,
        )
    ):
        types.append("supplier_concentration")
    if (
        re.search(
            r"\b(contract manufacturers?|outsourc|third-party manufactur)\w*\b",
            lowered,
        )
        and re.search(r"\b(rely|depend|outsourc)\w*\b", lowered)
    ):
        types.append("manufacturing_dependency")
    if (
        re.search(r"\b(concentrated|substantially all|majority|significant portion)\b", lowered)
        and re.search(r"\b(manufactur|assembl|production|facilit|operations)\b", lowered)
        and any(country.lower() in lowered for country in COUNTRIES)
    ):
        types.append("geographic_concentration")
    if (
        re.search(r"\b(raw material|component|semiconductor|ingredient|mineral)\b", lowered)
        and re.search(r"\b(shortage|limited|depend|rely|unavailable|constraint)\b", lowered)
    ):
        types.append("raw_material_dependency")
    if (
        re.search(
            r"\b(disrupt|shortage|delay|interruption|constraint|capacity|"
            r"natural disaster|pandemic|port closure|labor strike)\w*\b",
            lowered,
        )
        and SUPPLY_TERMS.search(evidence)
    ):
        types.append("supply_chain_disruption")
    if (
        re.search(r"\b(customer|customers)\b", lowered)
        and re.search(
            r"\b(concentration|largest customer|major customer|"
            r"accounted for|represented)\b",
            lowered,
        )
    ):
        types.append("customer_concentration")
    return types


def _severity(evidence: str) -> str:
    lowered = evidence.lower()
    if re.search(
        r"\b(sole|single[- ]source|substantially all|material adverse|"
        r"majority|significant disruption)\b",
        lowered,
    ):
        return "high"
    if re.search(
        r"\b(limited number|concentrated|significant portion|shortage|"
        r"delay|interruption|constraint)\b",
        lowered,
    ):
        return "medium"
    return "unknown"


def _customer_name(evidence: str) -> str | None:
    patterns = (
        re.compile(
            rf"\b({ORGANIZATION_NAME})\s+(?:accounted for|represented)\s+"
            r"\d{1,3}(?:\.\d+)?\s*%\s+of\s+(?:our|the company(?:'s|’s)?)"
        ),
        re.compile(
            rf"\b(?:customer|customers),?\s+(?:including|such as)\s+"
            rf"({ORGANIZATION_NAME})(?=[,.;])"
        ),
    )
    for pattern in patterns:
        match = pattern.search(evidence)
        if match:
            return _clean_name(match.group(1))
    return None


def _dedupe(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    output = []
    for item in items:
        key = tuple(item.get(field) for field in keys)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


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
        item_rank = (item.get("confidence", 0), item.get("filing_date") or "")
        existing_rank = (
            existing.get("confidence", 0),
            existing.get("filing_date") or "",
        ) if existing else (-1, "")
        if existing is None or item_rank > existing_rank:
            selected[key] = item
    return list(selected.values())


def _specific_material(material: str) -> bool:
    return _normalize_text(material).casefold() not in GENERIC_MATERIAL_TERMS


def _dedupe_risks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    selected: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get("type") or "").casefold().strip()
        if not key:
            continue
        existing = selected.get(key)
        rank = (
            severity_rank.get(item.get("severity"), 0),
            item.get("confidence", 0),
            item.get("filing_date") or "",
        )
        existing_rank = (
            severity_rank.get(existing.get("severity"), 0),
            existing.get("confidence", 0),
            existing.get("filing_date") or "",
        ) if existing else (-1, -1, "")
        if existing is None or rank > existing_rank:
            selected[key] = item
    return sorted(
        selected.values(),
        key=lambda item: (
            -severity_rank.get(item.get("severity"), 0),
            -float(item.get("confidence") or 0),
            str(item.get("type") or ""),
        ),
    )


def collect_supply_chain_passages(
    filings: list[dict[str, str]],
    limit_per_filing: int = 60,
) -> list[dict[str, Any]]:
    passages: list[dict[str, Any]] = []
    for filing in filings:
        parser = _FilingTextParser()
        parser.feed(filing["html"])
        parser.close()
        section: str | None = None
        filing_passages: list[dict[str, Any]] = []

        for block in parser.blocks:
            detected_section = _section_name(block)
            if detected_section:
                section = detected_section
                if len(block) <= 180:
                    continue
            for evidence in _sentences(block):
                if not SUPPLY_TERMS.search(evidence):
                    continue
                lowered = evidence.lower()
                score = 1
                if section in {
                    "risk_factors",
                    "business",
                    "manufacturing",
                    "supply_chain",
                    "suppliers",
                    "management_discussion_and_analysis",
                }:
                    score += 2
                if re.search(
                    r"\b(single[- ]source|sole[- ]source|contract manufactur|"
                    r"largest customer|accounted for|substantially all|"
                    r"limited number|concentrat|outsourc)\w*\b",
                    lowered,
                ):
                    score += 4
                if re.search(
                    r"\b(such as|including|include|from|by)\b",
                    lowered,
                ) and re.search(
                    r"\b(foundr|supplier|vendor|manufacturer|subcontractor|"
                    r"purchas|procur|sourc)\w*\b",
                    lowered,
                ):
                    score += 6
                if re.search(
                    r"\b(disrupt|shortage|delay|constraint|depend|rely)\w*\b",
                    lowered,
                ):
                    score += 2
                filing_passages.append(
                    {
                        "passage_id": (
                            f"{filing['accession']}:{len(filing_passages)}"
                        ),
                        "section": section,
                        "evidence": evidence,
                        "score": score,
                        "filing": filing,
                    }
                )

        selected = sorted(
            filing_passages,
            key=lambda item: (-item["score"], item["passage_id"]),
        )[:limit_per_filing]
        passages.extend(selected)
    return passages


def extract_supply_chain_exposure(
    ticker: str,
    filings: list[dict[str, str]],
) -> dict[str, Any]:
    suppliers: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    customers: list[dict[str, Any]] = []
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

            for evidence in _sentences(block):
                if not SUPPLY_TERMS.search(evidence):
                    continue
                source = _source_fields(filing, section, evidence)
                relationship_type = _relationship_type(evidence)

                for name in _supplier_names(evidence):
                    suppliers.append(
                        {
                            "name": name,
                            "role": _role(evidence, relationship_type),
                            "relationship_type": relationship_type,
                            "dependency_type": (
                                "single_source"
                                if re.search(
                                    r"\b(single[- ]source|sole[- ]source)\b",
                                    evidence,
                                    re.I,
                                )
                                else "disclosed_relationship"
                            ),
                            "percentage": _percentage(evidence),
                            **source,
                        }
                    )

                lowered = evidence.lower()
                if re.search(
                    r"\b(manufactur|assembl|production|facilit|fabricat)\w*\b",
                    lowered,
                ):
                    for country in COUNTRIES:
                        if re.search(rf"\b{re.escape(country)}\b", evidence, re.I):
                            locations.append(
                                {
                                    "country": country,
                                    "role": "manufacturing_or_operations_location",
                                    "percentage": _percentage(evidence),
                                    **source,
                                }
                            )

                for material in MATERIAL_TERMS:
                    if re.search(rf"\b{re.escape(material)}\b", evidence, re.I):
                        if _specific_material(material) and re.search(
                            r"\b(raw material|supply|source|"
                            r"availability|shortage|depend|rely|procure)\w*\b",
                            lowered,
                        ):
                            materials.append(
                                {
                                    "material": material,
                                    "dependency_type": (
                                        "single_source"
                                        if re.search(
                                            r"\b(single[- ]source|sole[- ]source)\b",
                                            lowered,
                                        )
                                        else "disclosed_dependency"
                                    ),
                                    "percentage": _percentage(evidence),
                                    **source,
                                }
                            )

                if (
                    re.search(r"\bcustomer(?:s)?\b", lowered)
                    and re.search(
                        r"\b(accounted for|represented|largest customer|"
                        r"customer concentration|major customer)\b",
                        lowered,
                    )
                ):
                    customers.append(
                        {
                            "name": _customer_name(evidence),
                            "percentage": _percentage(evidence),
                            "basis": (
                                "revenue"
                                if "revenue" in lowered or "sales" in lowered
                                else "not_specified"
                            ),
                            **source,
                        }
                    )

                for risk_type in _risk_types(evidence):
                    risks.append(
                        {
                            "type": risk_type,
                            "severity": _severity(evidence),
                            "percentage": _percentage(evidence),
                            **source,
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
            "extractor_version": SUPPLY_CHAIN_EXTRACTOR_VERSION,
            "cache_source": None,
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
        "supply_chain_exposure": {
            "suppliers": _dedupe_best(
                suppliers,
                ("name", "relationship_type"),
            ),
            "manufacturing_locations": _dedupe_best(
                locations,
                ("country",),
            ),
            "raw_material_dependencies": _dedupe_best(
                materials,
                ("material", "dependency_type"),
            ),
            "customer_concentrations": _dedupe(
                customers,
                ("name", "percentage", "evidence", "source_accession"),
            ),
            "risks": _dedupe_risks(risks),
        },
    }
