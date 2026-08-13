import json
import zipfile
from pathlib import Path

from app.providers.sec_13f import (
    _effective_accessions,
    convert_reported_value,
    get_institutional_holders,
    import_13f_archive,
    normalize_cusip,
)


def _write_tsv(archive: zipfile.ZipFile, name: str, rows: list[list[str]]) -> None:
    archive.writestr(name, "\n".join("\t".join(row) for row in rows) + "\n")


def _archive(
    path: Path,
    *,
    multiple_classes: bool = False,
    included_manager: bool = False,
) -> Path:
    submissions = [
        ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"],
        ["old-period", "14-FEB-2026", "13F-HR", "9", "31-DEC-2025"],
        ["original", "01-MAY-2026", "13F-HR", "1", "31-MAR-2026"],
        ["restatement", "10-MAY-2026", "13F-HR/A", "1", "31-MAR-2026"],
        ["manager-two", "12-MAY-2026", "13F-HR", "2", "31-MAR-2026"],
        ["manager-put", "13-MAY-2026", "13F-HR", "3", "31-MAR-2026"],
    ]
    cover = [
        [
            "ACCESSION_NUMBER", "REPORTCALENDARORQUARTER", "ISAMENDMENT",
            "AMENDMENTNO", "AMENDMENTTYPE", "FILINGMANAGER_NAME",
        ],
        ["old-period", "31-DEC-2025", "", "", "", "Old Manager"],
        ["original", "31-MAR-2026", "", "", "", "Manager One"],
        ["restatement", "31-MAR-2026", "Y", "1", "RESTATEMENT", "Manager One LLC"],
        ["manager-two", "31-MAR-2026", "", "", "", "Manager Two"],
        ["manager-put", "31-MAR-2026", "", "", "", "Options Manager"],
    ]
    header = [
        "ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS",
        "CUSIP", "FIGI", "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL",
        "INVESTMENTDISCRETION", "OTHERMANAGER", "VOTING_AUTH_SOLE",
        "VOTING_AUTH_SHARED", "VOTING_AUTH_NONE",
    ]
    info = [
        header,
        ["original", "1", "APPLE INC", "COM", "037833100", "", "1000", "100", "SH", "", "SOLE", "", "100", "0", "0"],
        ["restatement", "2", "APPLE INC", "COM", "037833100", "BBG000B9XRY4", "1800", "150", "SH", "", "SOLE", "", "150", "0", "0"],
        ["manager-two", "3", "APPLE INC", "COM", "037833100", "BBG000B9XRY4", "2400", "200", "SH", "", "SOLE", "1" if included_manager else "", "200", "0", "0"],
        ["manager-two", "4", "APPLE INC", "COM", "037833100", "BBG000B9XRY4", "600", "50", "SH", "", "SOLE", "", "50", "0", "0"],
        ["manager-two", "5", "APPLE INC", "COM", "037833100", "BBG000B9XRY4", "600", "50", "SH", "", "SOLE", "", "50", "0", "0"],
        ["manager-put", "6", "APPLE INC", "COM", "037833100", "", "900", "90", "SH", "PUT", "SOLE", "", "0", "0", "0"],
        ["manager-put", "bad", "BROKEN INC", "COM", "123456789", "", "not-a-number", "x", "SH", "", "SOLE", "", "0", "0", "0"],
    ]
    if multiple_classes:
        info.append(
            ["manager-two", "7", "APPLE INC", "CL A", "037833209", "", "100", "10", "SH", "", "SOLE", "", "10", "0", "0"]
        )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        _write_tsv(archive, "SUBMISSION.tsv", submissions)
        _write_tsv(archive, "COVERPAGE.tsv", cover)
        _write_tsv(archive, "INFOTABLE.tsv", info)
        if included_manager:
            _write_tsv(archive, "OTHERMANAGER2.tsv", [
                ["ACCESSION_NUMBER", "SEQUENCENUMBER", "CIK", "FORM13FFILENUMBER", "CRDNUMBER", "SECFILENUMBER", "NAME"],
                ["manager-two", "1", "22", "", "", "", "Included Manager"],
            ])
    return path


def test_latest_quarter_import_is_idempotent_and_resolves_restatement(tmp_path):
    archive = _archive(tmp_path / "fixture.zip")
    database = tmp_path / "13f.sqlite3"
    ticker_rows = [{"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193}]

    first = import_13f_archive(archive, database, ticker_rows=ticker_rows)
    second = import_13f_archive(archive, database, ticker_rows=ticker_rows)
    result = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
    )

    assert first.status == "imported"
    assert first.report_period == "2026-03-31"
    assert first.managers == 3
    assert first.holdings == 4
    assert first.malformed_rows == 1
    assert second.status == "unchanged"
    assert result.state == "available"
    assert result.total == 2
    assert [holder["shares_held"] for holder in result.holders] == [250, 150]
    assert result.holders[1]["institution_name"] == "Manager One LLC"
    assert all(holder["manager_cik"] != "0000000003" for holder in result.holders)


def test_query_paginates_aggregated_manager_rows(tmp_path):
    archive = _archive(tmp_path / "fixture.zip")
    database = tmp_path / "13f.sqlite3"
    import_13f_archive(
        archive,
        database,
        ticker_rows=[{"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193}],
    )

    result = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
        limit=1,
        offset=1,
    )

    assert result.total == 2
    assert len(result.holders) == 1
    assert result.holders[0]["shares_held"] == 150


def test_missing_database_and_unresolved_mapping_have_distinct_states(tmp_path):
    missing = get_institutional_holders(
        tmp_path / "missing.sqlite3",
        ticker="AAPL",
        company_cik="0000320193",
    )
    archive = _archive(tmp_path / "fixture.zip")
    database = tmp_path / "13f.sqlite3"
    import_13f_archive(archive, database)
    unresolved = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
    )

    assert missing.state == "temporarily_unavailable"
    assert unresolved.state == "identifier_mapping_required"


def test_low_confidence_manual_mapping_is_rejected(tmp_path):
    archive = _archive(tmp_path / "fixture.zip")
    database = tmp_path / "13f.sqlite3"
    mapping_file = tmp_path / "mappings.json"
    mapping_file.write_text(json.dumps({
        "mappings": [{
            "ticker": "LOW",
            "company_cik": "1",
            "cusip": "037833100",
            "issuer_name": "Apple Inc.",
            "class_title": "COM",
            "mapping_method": "issuer_name",
            "confidence": 0.6,
            "verified": False,
        }]
    }))
    import_13f_archive(archive, database, mapping_file=mapping_file)

    result = get_institutional_holders(
        database,
        ticker="LOW",
        company_cik="1",
    )

    assert result.state == "identifier_mapping_required"


def test_multiple_share_classes_require_explicit_mapping(tmp_path):
    archive = _archive(tmp_path / "classes.zip", multiple_classes=True)
    database = tmp_path / "13f.sqlite3"
    import_13f_archive(
        archive,
        database,
        ticker_rows=[{"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193}],
    )

    result = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
    )

    assert result.state == "identifier_mapping_required"


def test_verified_figi_mapping_can_resolve_without_cusip(tmp_path):
    archive = _archive(tmp_path / "fixture.zip")
    database = tmp_path / "13f.sqlite3"
    mapping_file = tmp_path / "mappings.json"
    mapping_file.write_text(json.dumps({
        "mappings": [{
            "ticker": "AAPL",
            "company_cik": "0000320193",
            "figi": "BBG000B9XRY4",
            "cusip": "037833100",
            "issuer_name": "Apple Inc.",
            "class_title": "COM",
            "mapping_method": "figi",
            "confidence": 1,
            "verified": True,
        }]
    }))
    import_13f_archive(archive, database, mapping_file=mapping_file)

    result = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
    )

    assert result.state == "available"
    assert result.mapping_method == "figi"


def test_cusip_and_value_unit_normalization():
    assert normalize_cusip("037833-100") == "037833100"
    assert normalize_cusip("bad") is None
    assert convert_reported_value("1250", "02-JAN-2023") == (
        1_250_000,
        "USD_THOUSANDS",
    )
    assert convert_reported_value("1250", "03-JAN-2023") == (1250, "USD")


def test_new_holdings_amendment_adds_while_restatement_replaces():
    base = {
        "manager_cik": "1",
        "report_period": "2026-03-31",
        "filing_date": "2026-05-01",
        "amendment_number": None,
        "submission_type": "13F-HR",
        "amendment_type": None,
        "accession_number": "base",
    }
    addition = {
        **base,
        "filing_date": "2026-05-02",
        "submission_type": "13F-HR/A",
        "amendment_type": "NEW HOLDINGS",
        "accession_number": "addition",
    }
    restatement = {
        **addition,
        "filing_date": "2026-05-03",
        "amendment_type": "RESTATEMENT",
        "accession_number": "restatement",
    }

    assert _effective_accessions([base, addition]) == {"base", "addition"}
    assert _effective_accessions([base, addition, restatement]) == {"restatement"}


def test_other_included_manager_sequence_controls_row_attribution(tmp_path):
    archive = _archive(tmp_path / "included.zip", included_manager=True)
    database = tmp_path / "13f.sqlite3"
    import_13f_archive(
        archive,
        database,
        ticker_rows=[{"ticker": "AAPL", "title": "Apple Inc.", "cik_str": 320193}],
    )

    result = get_institutional_holders(
        database,
        ticker="AAPL",
        company_cik="0000320193",
    )

    included = next(
        holder for holder in result.holders
        if holder["institution_name"] == "Included Manager"
    )
    assert included["manager_cik"] == "0000000022"
    assert included["shares_held"] == 200
