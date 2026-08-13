from app.models import WorkspaceSection


def unavailable_section(message: str) -> WorkspaceSection:
    return WorkspaceSection(
        status="unavailable",
        source=None,
        source_timestamp=None,
        message=message,
    )


def build_placeholder_sections() -> dict[str, WorkspaceSection]:
    return {
        "revenue_mix": unavailable_section("No revenue segment provider is configured yet."),
        "financial_statements": unavailable_section("No financial statement provider is configured yet."),
        "growth_charts": unavailable_section("Growth charts require provider financial history."),
        "market_news": unavailable_section("No news provider is configured yet."),
        "ai_summary": unavailable_section("AI summary waits for factual data and assumptions."),
        "dcf": WorkspaceSection(
            status="missing_input",
            source=None,
            source_timestamp=None,
            message="DCF requires editable assumptions, base revenue, cash, debt, and share count inputs.",
        ),
    }
