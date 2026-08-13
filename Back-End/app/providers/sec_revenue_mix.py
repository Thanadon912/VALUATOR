from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from itertools import combinations
import re
from typing import Any


REVENUE_CONCEPTS = {
    "revenue",
    "revenues",
    "salesrevenuenet",
    "revenuefromcontractswithcustomers",
    "revenuefromcontractwithcustomerexcludingassessedtax",
    "revenuefromcontractwithcustomerincludingassessedtax",
}

REVENUE_EXCLUSIONS = {
    "availableforsale",
    "businessacquisition",
    "contractwithcustomerliability",
    "costofrevenue",
    "deferred",
    "percentage",
    "proceeds",
    "remainingperformanceobligation",
}

MIX_AXIS_PATTERNS = (
    (
        "business_segments",
        (
            "statementbusinesssegmentsaxis",
            "operatingsegmentsaxis",
            "businessunitaxis",
        ),
    ),
    (
        "end_markets",
        (
            "marketsofcustomersaxis",
            "customermarketsaxis",
            "endmarketsaxis",
        ),
    ),
    (
        "products",
        (
            "productorserviceaxis",
            "productsorservicesaxis",
            "productsandservicesaxis",
        ),
    ),
    (
        "geography",
        (
            "statementgeographicalaxis",
            "geographicaxis",
            "geographyaxis",
            "geographicalareasaxis",
        ),
    ),
)

MEMBER_EXCLUSIONS = {
    "corporatenonsegmentmember",
    "operatingsegmentsmember",
}

MEMBER_LABEL_OVERRIDES = {
    "iphonemember": "iPhone",
    "ipadmember": "iPad",
    "macmember": "Mac",
    "servicemember": "Services",
    "wearableshomeandaccessoriesmember": "Wearables, Home and Accessories",
}


@dataclass(frozen=True)
class Dimension:
    axis: str
    member: str


@dataclass
class Context:
    start: str | None = None
    end: str | None = None
    dimensions: list[Dimension] = field(default_factory=list)


@dataclass(frozen=True)
class NumericFact:
    concept: str
    context_ref: str
    unit_ref: str | None
    value: float
    filing_date: str | None = None


class InlineXbrlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.contexts: dict[str, Context] = {}
        self.facts: list[NumericFact] = []
        self._context_id: str | None = None
        self._context: Context | None = None
        self._context_field: str | None = None
        self._dimension_axis: str | None = None
        self._text: list[str] = []
        self._fact_attrs: dict[str, str] | None = None
        self._fact_depth = 0
        self._fact_text: list[str] = []
        self._exclude_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {
            key.lower(): value
            for key, value in attrs
            if value is not None
        }
        lowered = tag.lower()

        if lowered == "xbrli:context":
            self._context_id = attributes.get("id")
            self._context = Context()
        elif self._context is not None and lowered in {
            "xbrli:startdate",
            "xbrli:enddate",
        }:
            self._context_field = lowered.rsplit(":", 1)[-1]
            self._text = []
        elif self._context is not None and lowered == "xbrldi:explicitmember":
            self._dimension_axis = attributes.get("dimension")
            self._text = []

        if lowered == "ix:nonfraction":
            self._fact_attrs = attributes
            self._fact_depth = 1
            self._fact_text = []
            self._exclude_depth = 0
        elif self._fact_attrs is not None:
            self._fact_depth += 1
            if lowered == "ix:exclude":
                self._exclude_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()

        if self._context is not None:
            if lowered in {"xbrli:startdate", "xbrli:enddate"}:
                value = "".join(self._text).strip()
                if self._context_field == "startdate":
                    self._context.start = value
                elif self._context_field == "enddate":
                    self._context.end = value
                self._context_field = None
                self._text = []
            elif lowered == "xbrldi:explicitmember":
                member = "".join(self._text).strip()
                if self._dimension_axis and member:
                    self._context.dimensions.append(
                        Dimension(self._dimension_axis, member)
                    )
                self._dimension_axis = None
                self._text = []
            elif lowered == "xbrli:context":
                if self._context_id:
                    self.contexts[self._context_id] = self._context
                self._context_id = None
                self._context = None

        if self._fact_attrs is not None:
            if lowered == "ix:exclude" and self._exclude_depth:
                self._exclude_depth -= 1
            self._fact_depth -= 1
            if lowered == "ix:nonfraction" and self._fact_depth == 0:
                fact = _numeric_fact(self._fact_attrs, "".join(self._fact_text))
                if fact is not None:
                    self.facts.append(fact)
                self._fact_attrs = None
                self._fact_text = []

    def handle_data(self, data: str) -> None:
        if self._context_field or self._dimension_axis:
            self._text.append(data)
        if self._fact_attrs is not None and self._exclude_depth == 0:
            self._fact_text.append(data)


def _numeric_fact(
    attributes: dict[str, str],
    raw_value: str,
) -> NumericFact | None:
    concept = attributes.get("name")
    context_ref = attributes.get("contextref")
    if not concept or not context_ref:
        return None

    normalized = raw_value.strip().replace(",", "").replace("$", "")
    normalized = normalized.replace("\u2212", "-").replace("\xa0", "")
    if normalized in {"", "-", "—", "–"}:
        return None
    negative = normalized.startswith("(") and normalized.endswith(")")
    if negative:
        normalized = normalized[1:-1]
    try:
        value = float(normalized)
        value *= 10 ** int(attributes.get("scale", "0"))
    except (TypeError, ValueError):
        return None
    if negative or attributes.get("sign") == "-":
        value = -abs(value)
    return NumericFact(
        concept=concept,
        context_ref=context_ref,
        unit_ref=attributes.get("unitref"),
        value=value,
    )


def _local_name(value: str) -> str:
    return value.rsplit(":", 1)[-1]


def _axis_type(axis: str) -> str | None:
    local = _local_name(axis).lower()
    for mix_type, patterns in MIX_AXIS_PATTERNS:
        if any(pattern in local for pattern in patterns):
            return mix_type
    return None


def _looks_like_geographic_mix(members: set[str] | dict[str, Any]) -> bool:
    labels = [_humanize_member(member).lower() for member in members]
    if len(labels) < 2:
        return False
    geographic_terms = re.compile(
        r"\b(africa|america|americas|asia|australia|canada|china|europe|"
        r"geographic|international|japan|korea|latin|middle east|"
        r"new zealand|north america|south america|united states)\b",
        re.I,
    )
    return all(geographic_terms.search(label) for label in labels)


def _is_revenue_concept(concept: str) -> bool:
    local = _local_name(concept).lower()
    if any(excluded in local for excluded in REVENUE_EXCLUSIONS):
        return False
    return local in REVENUE_CONCEPTS or (
        ("revenue" in local or "netsales" in local)
        and "cost" not in local
    )


def _humanize_member(member: str) -> str:
    local = _local_name(member)
    override = MEMBER_LABEL_OVERRIDES.get(local.lower())
    if override:
        return override
    local = re.sub(r"(Segment)?Member$", "", local)
    words = re.findall(
        r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|\d+",
        local,
    )
    label = " ".join(words).strip()
    return re.sub(r"\bAnd\b", "&", label) or local


def _valid_duration(context: Context) -> bool:
    if not context.start or not context.end:
        return False
    try:
        days = (date.fromisoformat(context.end) - date.fromisoformat(context.start)).days
    except ValueError:
        return False
    return 300 <= days <= 380


def _currency_code(unit_ref: str | None) -> str | None:
    if unit_ref is None:
        return None
    lowered = unit_ref.lower()
    if any(
        token in lowered
        for token in ("share", "pure", "number", "percent", "ratio")
    ):
        return None
    matches = re.findall(r"(?:^|[^a-z])([a-z]{3})(?:$|[^a-z])", lowered)
    if matches:
        return matches[-1].upper()
    if re.fullmatch(r"[a-z]{3}", lowered):
        return lowered.upper()
    return "CURRENCY" if "currency" in lowered else None


def _best_reconciling_subset(
    values: dict[str, float],
    total_revenue: float,
    tolerance: float = 0.03,
) -> tuple[list[tuple[str, float]], float] | None:
    eligible = [
        (member, value)
        for member, value in values.items()
        if value > 0 and _local_name(member).lower() not in MEMBER_EXCLUSIONS
    ]
    if len(eligible) < 2 or total_revenue <= 0:
        return None

    if len(eligible) > 18:
        eligible = sorted(eligible, key=lambda item: item[1], reverse=True)[:18]

    matches: list[tuple[float, int, list[tuple[str, float]]]] = []
    for size in range(2, len(eligible) + 1):
        for subset in combinations(eligible, size):
            error = abs(sum(value for _, value in subset) - total_revenue) / total_revenue
            if error <= tolerance:
                matches.append((error, -size, list(subset)))
    if not matches:
        return None
    error, _, subset = min(matches, key=lambda item: (item[0], item[1]))
    return subset, error


def _dimension_subset(
    dimension: str,
    values: dict[str, float],
    total_revenue: float,
) -> tuple[list[tuple[str, float]], float, bool] | None:
    reconciled = _best_reconciling_subset(values, total_revenue)
    if reconciled is not None:
        subset, error = reconciled
        return subset, error, True
    if dimension != "geography" or total_revenue <= 0:
        return None

    explicit = [
        (member, value)
        for member, value in values.items()
        if 0 < value <= total_revenue
        and _local_name(member).lower() not in MEMBER_EXCLUSIONS
    ]
    if not explicit or sum(value for _, value in explicit) > total_revenue * 1.03:
        return None
    explicit.sort(key=lambda item: item[1], reverse=True)
    coverage_error = abs(
        sum(value for _, value in explicit) - total_revenue
    ) / total_revenue
    return explicit, coverage_error, False


def _totals_by_end(
    contexts: dict[str, Context],
    facts: list[NumericFact],
    reported_totals: list[dict[str, Any]],
) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = {}
    for row in reported_totals:
        currency = _currency_code(row.get("unit"))
        if row.get("end") and row.get("value") is not None and currency:
            totals[(row["end"], currency)] = float(row["value"])
    for fact in facts:
        context = contexts.get(fact.context_ref)
        currency = _currency_code(fact.unit_ref)
        if (
            context is None
            or context.dimensions
            or not context.end
            or not _valid_duration(context)
            or not _is_revenue_concept(fact.concept)
            or currency is None
        ):
            continue
        totals.setdefault((context.end, currency), fact.value)
    return totals


def _item_alias(dimension: str) -> str:
    return {
        "business_segments": "segment",
        "products": "product",
        "geography": "region",
        "end_markets": "end_market",
    }[dimension]


def _normalized_period(
    end: str,
    subset: list[tuple[str, float]],
    total_revenue: float,
    *,
    dimension: str,
    axis: str,
    concept: str,
    currency: str,
    confidence: float,
    source: str,
    source_url: str | None,
    filing_date: str | None,
    reconciled: bool,
) -> dict[str, Any]:
    alias = _item_alias(dimension)
    items = []
    for member, value in sorted(
        subset,
        key=lambda item: item[1],
        reverse=True,
    ):
        name = _humanize_member(member)
        item = {
            "name": name,
            alias: name,
            "member": member,
            "revenue": round(value),
            "percentage": round((value / total_revenue) * 100, 1),
            "currency": currency,
            "period_end": end,
            "confidence": confidence,
            "evidence": (
                f"SEC XBRL fact {concept} reports {name} revenue of "
                f"{round(value)} {currency} for the fiscal period ending "
                f"{end}; "
                + (
                    "the selected dimension reconciles to reported total "
                    "revenue."
                    if reconciled
                    else "the percentage is calculated against reported "
                    "total revenue, but the filing discloses only partial "
                    "geographic coverage."
                )
            ),
            "filing_url": source_url,
            "filing_date": filing_date,
            "source": source,
            "axis": axis,
            "concept": concept,
            "coverage": "complete" if reconciled else "partial",
        }
        items.append(item)
    return {
        "fiscal_year": int(end[:4]),
        "period_end": end,
        "total_revenue": round(total_revenue),
        "currency": currency,
        "items": items,
    }


def _extract_from_parsed_facts(
    ticker: str,
    contexts: dict[str, Context],
    facts: list[NumericFact],
    reported_totals: list[dict[str, Any]],
    source: str,
    source_url: str | None = None,
    filing_date: str | None = None,
) -> dict[str, Any]:
    totals = _totals_by_end(contexts, facts, reported_totals)
    grouped: dict[
        tuple[str, str, str, str, str],
        dict[str, set[float]],
    ] = {}

    for fact in facts:
        context = contexts.get(fact.context_ref)
        currency = _currency_code(fact.unit_ref)
        if (
            context is None
            or not context.end
            or not _valid_duration(context)
            or not _is_revenue_concept(fact.concept)
            or currency is None
        ):
            continue
        relevant = [
            dimension
            for dimension in context.dimensions
            if _axis_type(dimension.axis) is not None
        ]
        if len(relevant) != 1:
            continue
        dimension = relevant[0]
        mix_type = _axis_type(dimension.axis)
        if mix_type is None:
            continue
        key = (
            mix_type,
            dimension.axis,
            fact.concept,
            context.end,
            currency,
        )
        grouped.setdefault(key, {}).setdefault(dimension.member, set()).add(
            fact.value
        )

    candidates: list[
        tuple[
            int,
            float,
            int,
            str,
            str,
            str,
            str,
            str,
            list[tuple[str, float]],
            bool,
        ]
    ] = []
    priority = {name: index for index, (name, _) in enumerate(MIX_AXIS_PATTERNS)}
    for (
        source_mix_type,
        axis,
        concept,
        end,
        currency,
    ), member_values in grouped.items():
        total = totals.get((end, currency))
        if total is None or any(len(values) != 1 for values in member_values.values()):
            continue
        values = {
            member: next(iter(reported))
            for member, reported in member_values.items()
        }
        mix_type = (
            "geography"
            if source_mix_type == "business_segments"
            and _looks_like_geographic_mix(member_values)
            else source_mix_type
        )
        match = _dimension_subset(mix_type, values, total)
        if match is None:
            continue
        subset, error, reconciled = match
        candidates.append(
            (
                priority[mix_type],
                error,
                -len(subset),
                end,
                mix_type,
                axis,
                concept,
                currency,
                subset,
                reconciled,
            )
        )

    dimensions = {
        "business_segments": [],
        "products": [],
        "geography": [],
        "end_markets": [],
    }
    dimension_periods = {name: [] for name in dimensions}
    dimension_metadata: dict[str, dict[str, Any]] = {}

    for dimension in dimensions:
        dimension_candidates = [
            candidate for candidate in candidates if candidate[4] == dimension
        ]
        if not dimension_candidates:
            continue
        latest_end = max(candidate[3] for candidate in dimension_candidates)
        selected = min(
            (
                candidate
                for candidate in dimension_candidates
                if candidate[3] == latest_end
            ),
            key=lambda item: (item[0], item[1], item[2]),
        )
        (
            _,
            latest_error,
            _,
            _,
            _,
            axis,
            concept,
            currency,
            latest_subset,
            latest_reconciled,
        ) = selected
        confidence = (
            0.95
            if latest_reconciled and latest_error <= 0.01
            else 0.8
            if latest_reconciled
            else 0.75
        )
        effective_filing_date = filing_date or max(
            (
                fact.filing_date
                for fact in facts
                if fact.filing_date
                and fact.concept == concept
                and contexts.get(fact.context_ref)
                and contexts[fact.context_ref].end == latest_end
            ),
            default=None,
        )

        periods: list[dict[str, Any]] = []
        for (
            source_dimension,
            candidate_axis,
            candidate_concept,
            end,
            candidate_currency,
        ), member_values in grouped.items():
            normalized_dimension = (
                "geography"
                if source_dimension == "business_segments"
                and _looks_like_geographic_mix(member_values)
                else source_dimension
            )
            if (
                normalized_dimension != dimension
                or candidate_axis != axis
                or candidate_concept != concept
                or candidate_currency != currency
                or (end, currency) not in totals
                or any(len(values) != 1 for values in member_values.values())
            ):
                continue
            values = {
                member: next(iter(reported))
                for member, reported in member_values.items()
            }
            match = _dimension_subset(
                dimension,
                values,
                totals[(end, currency)],
            )
            if match is None:
                continue
            subset, error, reconciled = match
            periods.append(
                _normalized_period(
                    end,
                    subset,
                    totals[(end, currency)],
                    dimension=dimension,
                    axis=axis,
                    concept=concept,
                    currency=currency,
                    confidence=(
                        0.95
                        if reconciled and error <= 0.01
                        else 0.8
                        if reconciled
                        else 0.75
                    ),
                    source=source,
                    source_url=source_url,
                    filing_date=effective_filing_date,
                    reconciled=reconciled,
                )
            )

        periods.sort(key=lambda period: period["period_end"])
        periods = periods[-5:]
        latest = _normalized_period(
            latest_end,
            latest_subset,
            totals[(latest_end, currency)],
            dimension=dimension,
            axis=axis,
            concept=concept,
            currency=currency,
            confidence=confidence,
            source=source,
            source_url=source_url,
            filing_date=effective_filing_date,
            reconciled=latest_reconciled,
        )
        dimensions[dimension] = latest["items"]
        dimension_periods[dimension] = periods
        dimension_metadata[dimension] = {
            "total_revenue": latest["total_revenue"],
            "currency": currency,
            "axis": axis,
            "concept": concept,
            "source": source,
            "coverage": "complete" if latest_reconciled else "partial",
        }

    if not any(dimensions.values()):
        return {}

    fiscal_year = max(
        item["period_end"][:4]
        for items in dimensions.values()
        for item in items
    )
    return {
        "ticker": ticker,
        "fiscal_year": int(fiscal_year),
        "revenue_mix": dimensions,
        "periods": dimension_periods,
        "dimension_metadata": dimension_metadata,
    }


def extract_revenue_mix_from_inline_xbrl(
    ticker: str,
    filing_html: str,
    reported_totals: list[dict[str, Any]],
    *,
    filing_url: str | None = None,
    filing_date: str | None = None,
) -> dict[str, Any]:
    parser = InlineXbrlParser()
    parser.feed(filing_html)
    parser.close()
    return _extract_from_parsed_facts(
        ticker=ticker,
        contexts=parser.contexts,
        facts=parser.facts,
        reported_totals=reported_totals,
        source="sec_filing_inline_xbrl",
        source_url=filing_url,
        filing_date=filing_date,
    )


def extract_revenue_mix_from_companyfacts(
    ticker: str,
    companyfacts: dict[str, Any],
    reported_totals: list[dict[str, Any]],
    *,
    source_url: str | None = None,
) -> dict[str, Any]:
    contexts: dict[str, Context] = {}
    facts: list[NumericFact] = []
    row_index = 0

    for namespace in companyfacts.get("facts", {}).values():
        for concept, payload in namespace.items():
            searchable = " ".join(
                str(payload.get(field, ""))
                for field in ("label", "description")
            )
            if not _is_revenue_concept(concept) and not _is_revenue_concept(searchable):
                continue
            for unit, rows in payload.get("units", {}).items():
                for row in rows:
                    raw_dimensions = row.get("dimensions")
                    if not isinstance(raw_dimensions, dict):
                        continue
                    dimensions = [
                        Dimension(str(axis), str(member))
                        for axis, member in raw_dimensions.items()
                        if member
                    ]
                    if not dimensions or row.get("val") is None:
                        continue
                    context_ref = f"companyfacts-{row_index}"
                    row_index += 1
                    contexts[context_ref] = Context(
                        start=row.get("start"),
                        end=row.get("end"),
                        dimensions=dimensions,
                    )
                    facts.append(
                        NumericFact(
                            concept=concept,
                            context_ref=context_ref,
                            unit_ref=unit,
                            value=float(row["val"]),
                            filing_date=row.get("filed"),
                        )
                    )

    return _extract_from_parsed_facts(
        ticker=ticker,
        contexts=contexts,
        facts=facts,
        reported_totals=reported_totals,
        source="sec_companyfacts",
        source_url=source_url,
    )
