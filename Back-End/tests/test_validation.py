import pytest

from app.core.validation import normalize_ticker


from tests.allure_helpers import valuator_test

@pytest.mark.parametrize(
    "raw,expected",
    [("aapl", "AAPL"), (" brk.b ", "BRK.B"), ("tsla", "TSLA")],
)
@valuator_test(
    epic="API Contract",
    feature="Validation",
    story="Ticker Normalization",
    priority="P1",
    severity="normal",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-API-001"
)
def test_normalize_ticker_accepts_common_symbols(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "two words", "AAPL!", "TOO-LONG-123"])
def test_normalize_ticker_rejects_invalid_symbols(raw):
    with pytest.raises(ValueError):
        normalize_ticker(raw)
