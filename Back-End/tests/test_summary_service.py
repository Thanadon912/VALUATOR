from app.services.summary import _instant_value


def test_instant_value_tolerates_explicit_null_fact() -> None:
    assert _instant_value({"shares": None}, "shares") is None


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Summary & Fundamentals",
    feature="Instant Value",
    story="Fact Value Extraction",
    priority="P0",
    severity="critical",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-SUM-001"
)
def test_instant_value_returns_fact_value() -> None:
    assert _instant_value({"shares": {"value": 123.0}}, "shares") == 123.0
