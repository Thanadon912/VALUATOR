from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx


SEC_13F_DATASETS_PAGE = (
    "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
)
SEC_13F_ARCHIVE_BASE = (
    "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/"
)
SEC_FILING_INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/"
    "{accession}-index.html"
)
VALUE_USD_EFFECTIVE_DATE = date(2023, 1, 3)
IMPORTER_VERSION = "sec-13f-v4"
COMMON_CLASS_MARKERS = {
    "COM",
    "COMMON",
    "COMMON STOCK",
    "COMMON SHARES",
    "ORD",
    "ORDINARY SHARES",
    "CL A",
    "CL B",
    "CLASS A",
    "CLASS B",
}


@dataclass(frozen=True)
class ImportStats:
    status: str
    report_period: str | None
    managers: int
    holdings: int
    mapped_holdings: int
    unresolved_holdings: int
    malformed_rows: int
    archive_sha256: str


@dataclass(frozen=True)
class InstitutionalQueryResult:
    state: str
    report_period: str | None
    holders: list[dict[str, Any]]
    total: int
    institution_count: int
    total_shares: int | None
    security_identifiers: list[str]
    security_classes: list[str]
    mapping_method: str | None
    mapping_confidence: float | None
    warnings: list[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_cusip(value: str | None) -> str | None:
    normalized = re.sub(r"[^A-Z0-9*@#]", "", (value or "").upper())
    return normalized if len(normalized) == 9 else None


def normalize_figi(value: str | None) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return normalized if len(normalized) == 12 else None


def normalize_issuer_name(value: str | None) -> str:
    text = (value or "").upper().replace("&", " AND ")
    text = re.sub(r"\b(INCORPORATED|INCORPORATION|CORPORATION|CORP|INC|LTD|PLC)\b", " ", text)
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def normalize_class_title(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", (value or "").upper()).strip()


def is_common_share_class(value: str | None) -> bool:
    normalized = normalize_class_title(value)
    return normalized in COMMON_CLASS_MARKERS or normalized.startswith("COM ")


def convert_reported_value(
    value: str | int | float | None,
    filing_date: str | date,
) -> tuple[float | None, str]:
    if value in {None, ""}:
        return None, "USD"
    filed = (
        filing_date
        if isinstance(filing_date, date)
        else _parse_sec_date(filing_date)
    )
    number = float(value)
    if filed < VALUE_USD_EFFECTIVE_DATE:
        return number * 1000, "USD_THOUSANDS"
    return number, "USD"


def _parse_sec_date(value: str) -> date:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.title(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported SEC date: {value}")


def _iso_date(value: str) -> str:
    return _parse_sec_date(value).isoformat()


def _number(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def _integer(value: str | None) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tsv_rows(archive: zipfile.ZipFile, filename: str) -> Iterable[dict[str, str]]:
    with archive.open(filename) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            yield from csv.DictReader(text, delimiter="\t")


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;

        CREATE TABLE import_manifest (
            id INTEGER PRIMARY KEY,
            archive_name TEXT NOT NULL,
            archive_sha256 TEXT NOT NULL UNIQUE,
            importer_version TEXT NOT NULL,
            source_url TEXT,
            report_period TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            manager_count INTEGER NOT NULL,
            holding_count INTEGER NOT NULL,
            mapped_holding_count INTEGER NOT NULL,
            unresolved_holding_count INTEGER NOT NULL,
            malformed_row_count INTEGER NOT NULL
        );

        CREATE TABLE managers (
            manager_cik TEXT NOT NULL,
            report_period TEXT NOT NULL,
            manager_name TEXT NOT NULL,
            PRIMARY KEY (manager_cik, report_period)
        );

        CREATE TABLE submissions (
            accession_number TEXT PRIMARY KEY,
            filing_date TEXT NOT NULL,
            submission_type TEXT NOT NULL,
            manager_cik TEXT NOT NULL,
            report_period TEXT NOT NULL,
            manager_name TEXT NOT NULL,
            amendment_type TEXT,
            amendment_number INTEGER,
            source_url TEXT NOT NULL,
            is_effective INTEGER NOT NULL,
            FOREIGN KEY (manager_cik, report_period)
                REFERENCES managers(manager_cik, report_period)
        );

        CREATE TABLE holdings (
            id INTEGER PRIMARY KEY,
            accession_number TEXT NOT NULL,
            infotable_sk TEXT NOT NULL,
            filing_manager_cik TEXT NOT NULL,
            manager_cik TEXT NOT NULL,
            manager_name TEXT NOT NULL,
            issuer_name TEXT NOT NULL,
            normalized_issuer_name TEXT NOT NULL,
            class_title TEXT,
            normalized_class_title TEXT NOT NULL,
            cusip TEXT,
            figi TEXT,
            shares_held INTEGER,
            share_type TEXT,
            reported_value REAL,
            reported_value_unit TEXT NOT NULL,
            reported_value_usd REAL,
            put_call TEXT,
            investment_discretion TEXT,
            voting_sole INTEGER,
            voting_shared INTEGER,
            voting_none INTEGER,
            report_period TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            source_url TEXT NOT NULL
        );

        CREATE TABLE security_mappings (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            company_cik TEXT,
            cusip TEXT,
            figi TEXT,
            issuer_name TEXT NOT NULL,
            normalized_issuer_name TEXT NOT NULL,
            class_title TEXT,
            normalized_class_title TEXT NOT NULL,
            mapping_method TEXT NOT NULL,
            confidence REAL NOT NULL,
            verified INTEGER NOT NULL
        );

        CREATE TABLE manager_portfolio_totals (
            manager_cik TEXT NOT NULL,
            report_period TEXT NOT NULL,
            reported_value_usd REAL,
            PRIMARY KEY (manager_cik, report_period)
        );

        CREATE INDEX idx_holdings_cusip ON holdings(cusip);
        CREATE INDEX idx_holdings_figi ON holdings(figi);
        CREATE INDEX idx_holdings_issuer ON holdings(normalized_issuer_name);
        CREATE INDEX idx_holdings_manager ON holdings(manager_cik);
        CREATE INDEX idx_holdings_period ON holdings(report_period);
        CREATE UNIQUE INDEX uq_holding_row ON holdings(
            accession_number, manager_cik, IFNULL(cusip, ''),
            IFNULL(figi, ''), normalized_class_title, IFNULL(shares_held, -1),
            IFNULL(reported_value, -1), IFNULL(put_call, ''),
            IFNULL(investment_discretion, '')
        );
        CREATE INDEX idx_mappings_ticker ON security_mappings(ticker);
        CREATE INDEX idx_mappings_company_cik ON security_mappings(company_cik);
        CREATE INDEX idx_mappings_cusip ON security_mappings(cusip);
        CREATE INDEX idx_mappings_figi ON security_mappings(figi);
        CREATE UNIQUE INDEX uq_security_mapping ON security_mappings(
            ticker, IFNULL(cusip, ''), IFNULL(figi, ''),
            normalized_issuer_name, normalized_class_title
        );
        """
    )


def _load_manual_mappings(path: str | Path | None) -> list[dict[str, Any]]:
    if not path or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload.get("mappings") or []


def _effective_accessions(
    submissions: list[dict[str, Any]],
) -> set[str]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for submission in submissions:
        grouped[
            (submission["manager_cik"], submission["report_period"])
        ].append(submission)

    effective: set[str] = set()
    for rows in grouped.values():
        rows.sort(
            key=lambda row: (
                row["filing_date"],
                row.get("amendment_number") or 0,
                row["accession_number"],
            )
        )
        selected: list[str] = []
        for row in rows:
            if row["submission_type"] == "13F-HR":
                selected = [row["accession_number"]]
                continue
            amendment_type = (row.get("amendment_type") or "").upper()
            if "NEW HOLDINGS" in amendment_type:
                selected.append(row["accession_number"])
            else:
                # A restatement replaces the earlier table. An amendment with
                # missing semantics is also treated as replacement to avoid
                # silently double counting the original filing.
                selected = [row["accession_number"]]
        effective.update(selected)
    return effective


def _insert_mapping(
    connection: sqlite3.Connection,
    mapping: dict[str, Any],
) -> None:
    issuer_name = str(mapping.get("issuer_name") or "")
    class_title = str(mapping.get("class_title") or "")
    connection.execute(
        """
        INSERT OR IGNORE INTO security_mappings (
            ticker, company_cik, cusip, figi, issuer_name,
            normalized_issuer_name, class_title, normalized_class_title,
            mapping_method, confidence, verified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(mapping["ticker"]).upper(),
            str(mapping.get("company_cik") or "") or None,
            normalize_cusip(mapping.get("cusip")),
            normalize_figi(mapping.get("figi")),
            issuer_name,
            normalize_issuer_name(issuer_name),
            class_title or None,
            normalize_class_title(class_title),
            mapping.get("mapping_method") or "manual",
            float(mapping.get("confidence", 1)),
            1 if mapping.get("verified", True) else 0,
        ),
    )


def _build_exact_issuer_mappings(
    connection: sqlite3.Connection,
    ticker_rows: Iterable[dict[str, Any]],
) -> None:
    companies: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ticker_rows:
        normalized = normalize_issuer_name(row.get("title"))
        if normalized:
            companies[normalized].append(row)

    holdings = connection.execute(
        """
        SELECT normalized_issuer_name, issuer_name, class_title, cusip,
               COUNT(*) AS row_count
        FROM holdings
        WHERE COALESCE(put_call, '') = '' AND cusip IS NOT NULL
        GROUP BY normalized_issuer_name, cusip, class_title
        """
    ).fetchall()
    by_issuer: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for holding in holdings:
        if not is_common_share_class(holding["class_title"]):
            continue
        issuer = holding["normalized_issuer_name"]
        cusip = holding["cusip"]
        security = by_issuer[issuer].setdefault(
            cusip,
            {
                "cusip": cusip,
                "issuer_name": holding["issuer_name"],
                "class_title": holding["class_title"],
                "row_count": 0,
            },
        )
        security["row_count"] += int(holding["row_count"])

    for issuer, securities in by_issuer.items():
        company_rows = companies.get(issuer) or []
        security_rows = list(securities.values())
        if len(company_rows) != 1 or not security_rows:
            continue
        total_rows = sum(int(row["row_count"]) for row in security_rows)
        security = max(security_rows, key=lambda row: int(row["row_count"]))
        dominance = int(security["row_count"]) / total_rows
        if dominance < 0.98:
            continue
        company = company_rows[0]
        _insert_mapping(
            connection,
            {
                "ticker": company["ticker"],
                "company_cik": f"{int(company['cik_str']):010d}",
                "cusip": security["cusip"],
                "figi": None,
                "issuer_name": security["issuer_name"],
                "class_title": security["class_title"],
                "mapping_method": "issuer_name",
                "confidence": 0.98,
                "verified": False,
            },
        )


def import_13f_archive(
    archive_path: str | Path,
    database_path: str | Path,
    *,
    source_url: str | None = None,
    mapping_file: str | Path | None = None,
    ticker_rows: Iterable[dict[str, Any]] = (),
) -> ImportStats:
    archive_path = Path(archive_path)
    database_path = Path(database_path)
    archive_digest = _sha256(archive_path)
    if database_path.exists():
        try:
            with sqlite3.connect(database_path) as existing:
                row = existing.execute(
                    "SELECT report_period, manager_count, holding_count, "
                    "mapped_holding_count, unresolved_holding_count, "
                    "malformed_row_count FROM import_manifest "
                    "WHERE archive_sha256 = ? AND importer_version = ?",
                    (archive_digest, IMPORTER_VERSION),
                ).fetchone()
            if row:
                return ImportStats(
                    status="unchanged",
                    report_period=row[0],
                    managers=row[1],
                    holdings=row[2],
                    mapped_holdings=row[3],
                    unresolved_holdings=row[4],
                    malformed_rows=row[5],
                    archive_sha256=archive_digest,
                )
        except sqlite3.DatabaseError:
            pass

    database_path.parent.mkdir(parents=True, exist_ok=True)
    temp_handle = tempfile.NamedTemporaryFile(
        prefix="13f-",
        suffix=".sqlite3",
        dir=database_path.parent,
        delete=False,
    )
    temp_handle.close()
    temp_path = Path(temp_handle.name)
    malformed_rows = 0
    try:
        connection = sqlite3.connect(temp_path)
        connection.row_factory = sqlite3.Row
        _schema(connection)
        with zipfile.ZipFile(archive_path) as archive:
            submission_rows = list(_tsv_rows(archive, "SUBMISSION.tsv"))
            cover_by_accession = {
                row["ACCESSION_NUMBER"]: row
                for row in _tsv_rows(archive, "COVERPAGE.tsv")
            }
            eligible = [
                row
                for row in submission_rows
                if row["SUBMISSIONTYPE"] in {"13F-HR", "13F-HR/A"}
            ]
            if not eligible:
                raise ValueError("Archive contains no 13F-HR submissions.")
            latest_period = max(_iso_date(row["PERIODOFREPORT"]) for row in eligible)
            submissions: list[dict[str, Any]] = []
            for row in eligible:
                report_period = _iso_date(row["PERIODOFREPORT"])
                if report_period != latest_period:
                    continue
                cover = cover_by_accession.get(row["ACCESSION_NUMBER"], {})
                cik = str(row["CIK"]).zfill(10)
                accession = row["ACCESSION_NUMBER"]
                submissions.append(
                    {
                        "accession_number": accession,
                        "filing_date": _iso_date(row["FILING_DATE"]),
                        "submission_type": row["SUBMISSIONTYPE"],
                        "manager_cik": cik,
                        "report_period": report_period,
                        "manager_name": cover.get("FILINGMANAGER_NAME") or cik,
                        "amendment_type": cover.get("AMENDMENTTYPE") or None,
                        "amendment_number": _integer(cover.get("AMENDMENTNO")),
                        "source_url": SEC_FILING_INDEX_URL.format(
                            cik=int(cik),
                            accession_path=accession.replace("-", ""),
                            accession=accession,
                        ),
                    }
                )
            effective = _effective_accessions(submissions)
            submission_by_accession = {
                row["accession_number"]: row for row in submissions
            }
            included_managers: dict[tuple[str, str], dict[str, str]] = {}
            if "OTHERMANAGER2.tsv" in archive.namelist():
                for row in _tsv_rows(archive, "OTHERMANAGER2.tsv"):
                    sequence = row.get("SEQUENCENUMBER") or ""
                    cik = (row.get("CIK") or "").strip()
                    if not sequence or not cik:
                        continue
                    included_managers[
                        (row["ACCESSION_NUMBER"], sequence)
                    ] = {
                        "cik": cik.zfill(10),
                        "name": row.get("NAME") or cik,
                    }
            for row in submissions:
                connection.execute(
                    "INSERT OR IGNORE INTO managers VALUES (?, ?, ?)",
                    (
                        row["manager_cik"],
                        row["report_period"],
                        row["manager_name"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO submissions VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        row["accession_number"],
                        row["filing_date"],
                        row["submission_type"],
                        row["manager_cik"],
                        row["report_period"],
                        row["manager_name"],
                        row["amendment_type"],
                        row["amendment_number"],
                        row["source_url"],
                        1 if row["accession_number"] in effective else 0,
                    ),
                )

            insert_sql = """
                INSERT OR IGNORE INTO holdings (
                    accession_number, infotable_sk, filing_manager_cik,
                    manager_cik, manager_name,
                    issuer_name, normalized_issuer_name, class_title,
                    normalized_class_title, cusip, figi, shares_held,
                    share_type, reported_value, reported_value_unit,
                    reported_value_usd, put_call, investment_discretion,
                    voting_sole, voting_shared, voting_none, report_period,
                    filing_date, source_url
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
            """
            batch: list[tuple[Any, ...]] = []
            for row in _tsv_rows(archive, "INFOTABLE.tsv"):
                submission = submission_by_accession.get(row["ACCESSION_NUMBER"])
                if not submission or row["ACCESSION_NUMBER"] not in effective:
                    continue
                try:
                    included = included_managers.get(
                        (
                            row["ACCESSION_NUMBER"],
                            (row.get("OTHERMANAGER") or "").strip(),
                        )
                    )
                    reporting_cik = (
                        included["cik"]
                        if included
                        else submission["manager_cik"]
                    )
                    reporting_name = (
                        included["name"]
                        if included
                        else submission["manager_name"]
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO managers VALUES (?, ?, ?)",
                        (
                            reporting_cik,
                            submission["report_period"],
                            reporting_name,
                        ),
                    )
                    reported_value = _number(row.get("VALUE"))
                    value_usd, value_unit = convert_reported_value(
                        reported_value,
                        submission["filing_date"],
                    )
                    batch.append(
                        (
                            row["ACCESSION_NUMBER"],
                            row["INFOTABLE_SK"],
                            submission["manager_cik"],
                            reporting_cik,
                            reporting_name,
                            row["NAMEOFISSUER"].strip(),
                            normalize_issuer_name(row["NAMEOFISSUER"]),
                            row.get("TITLEOFCLASS") or None,
                            normalize_class_title(row.get("TITLEOFCLASS")),
                            normalize_cusip(row.get("CUSIP")),
                            normalize_figi(row.get("FIGI")),
                            _integer(row.get("SSHPRNAMT")),
                            row.get("SSHPRNAMTTYPE") or None,
                            reported_value,
                            value_unit,
                            value_usd,
                            (row.get("PUTCALL") or "").upper() or None,
                            row.get("INVESTMENTDISCRETION") or None,
                            _integer(row.get("VOTING_AUTH_SOLE")),
                            _integer(row.get("VOTING_AUTH_SHARED")),
                            _integer(row.get("VOTING_AUTH_NONE")),
                            submission["report_period"],
                            submission["filing_date"],
                            submission["source_url"],
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    malformed_rows += 1
                    continue
                if len(batch) >= 5000:
                    connection.executemany(insert_sql, batch)
                    batch.clear()
            if batch:
                connection.executemany(insert_sql, batch)

        for mapping in _load_manual_mappings(mapping_file):
            _insert_mapping(connection, mapping)
        _build_exact_issuer_mappings(connection, ticker_rows)
        connection.execute(
            """
            INSERT INTO manager_portfolio_totals (
                manager_cik, report_period, reported_value_usd
            )
            SELECT manager_cik, report_period, SUM(reported_value_usd)
            FROM (
                SELECT manager_cik, report_period, cusip, figi, class_title,
                       shares_held, reported_value_usd, investment_discretion
                FROM holdings
                WHERE COALESCE(put_call, '') = ''
                GROUP BY manager_cik, report_period, cusip, figi, class_title,
                         shares_held, reported_value_usd, investment_discretion
            )
            GROUP BY manager_cik, report_period
            """
        )

        manager_count = connection.execute(
            "SELECT COUNT(*) FROM managers"
        ).fetchone()[0]
        holding_count = connection.execute(
            "SELECT COUNT(*) FROM holdings"
        ).fetchone()[0]
        mapped_count = connection.execute(
            """
            SELECT COUNT(DISTINCT h.id)
            FROM holdings h
            JOIN security_mappings m
              ON (m.cusip IS NOT NULL AND m.cusip = h.cusip)
              OR (m.figi IS NOT NULL AND m.figi = h.figi)
            """
        ).fetchone()[0]
        unresolved_count = holding_count - mapped_count
        connection.execute(
            """
            INSERT INTO import_manifest (
                archive_name, archive_sha256, importer_version, source_url, report_period,
                imported_at, manager_count, holding_count,
                mapped_holding_count, unresolved_holding_count,
                malformed_row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                archive_path.name,
                archive_digest,
                IMPORTER_VERSION,
                source_url,
                latest_period,
                _utc_now(),
                manager_count,
                holding_count,
                mapped_count,
                unresolved_count,
                malformed_rows,
            ),
        )
        connection.commit()
        connection.execute("PRAGMA optimize")
        connection.close()
        os.replace(temp_path, database_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return ImportStats(
        status="imported",
        report_period=latest_period,
        managers=manager_count,
        holdings=holding_count,
        mapped_holdings=mapped_count,
        unresolved_holdings=unresolved_count,
        malformed_rows=malformed_rows,
        archive_sha256=archive_digest,
    )


def discover_latest_archive_url(
    user_agent: str,
    timeout_seconds: float = 30,
) -> str:
    response = httpx.get(
        SEC_13F_DATASETS_PAGE,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
        follow_redirects=True,
    )
    response.raise_for_status()
    match = re.search(
        r'href="([^"]+form13f\.zip)"',
        response.text,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("SEC 13F data-set page did not expose an archive link.")
    href = match.group(1)
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://www.sec.gov{href}"
    return f"{SEC_13F_ARCHIVE_BASE}{href}"


def download_archive(
    url: str,
    cache_dir: str | Path,
    user_agent: str,
    timeout_seconds: float = 180,
) -> Path:
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    destination = cache / filename
    if destination.exists() and zipfile.is_zipfile(destination):
        return destination
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout_seconds,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    if not zipfile.is_zipfile(temporary):
        temporary.unlink(missing_ok=True)
        raise ValueError("Downloaded SEC 13F archive is not a valid ZIP file.")
    os.replace(temporary, destination)
    return destination


def _mapping_rows(
    connection: sqlite3.Connection,
    ticker: str,
    company_cik: str | None,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT * FROM security_mappings
        WHERE ticker = ? OR (? IS NOT NULL AND company_cik = ?)
        ORDER BY verified DESC,
          CASE mapping_method
            WHEN 'exact_identifier' THEN 1
            WHEN 'figi' THEN 2
            WHEN 'issuer_name' THEN 3
            WHEN 'alias' THEN 4
            WHEN 'manual' THEN 0
            ELSE 5
          END,
          confidence DESC
        """,
        (ticker.upper(), company_cik, company_cik),
    ).fetchall()
    if not rows:
        return []
    highest = max(float(row["confidence"]) for row in rows)
    return [
        row
        for row in rows
        if row["verified"] or float(row["confidence"]) >= max(0.97, highest)
    ]


def get_institutional_holders(
    database_path: str | Path,
    *,
    ticker: str,
    company_cik: str | None,
    report_period: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> InstitutionalQueryResult:
    path = Path(database_path)
    if not path.exists():
        return InstitutionalQueryResult(
            state="temporarily_unavailable",
            report_period=None,
            holders=[],
            total=0,
            institution_count=0,
            total_shares=None,
            security_identifiers=[],
            security_classes=[],
            mapping_method=None,
            mapping_confidence=None,
            warnings=[
                "The latest SEC Form 13F quarter has not been ingested yet."
            ],
        )
    try:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        manifest = connection.execute(
            "SELECT report_period FROM import_manifest "
            "ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        if not manifest:
            raise sqlite3.DatabaseError("Missing import manifest")
        selected_period = report_period or manifest["report_period"]
        mappings = _mapping_rows(connection, ticker, company_cik)
        if not mappings:
            connection.close()
            return InstitutionalQueryResult(
                state="identifier_mapping_required",
                report_period=selected_period,
                holders=[],
                total=0,
                institution_count=0,
                total_shares=None,
                security_identifiers=[],
                security_classes=[],
                mapping_method=None,
                mapping_confidence=None,
                warnings=[
                    "The security could not be mapped reliably to a CUSIP or FIGI."
                ],
            )
        cusips = sorted({row["cusip"] for row in mappings if row["cusip"]})
        figis = sorted({row["figi"] for row in mappings if row["figi"]})
        conditions: list[str] = []
        parameters: list[Any] = [selected_period]
        if cusips:
            conditions.append(f"cusip IN ({','.join('?' for _ in cusips)})")
            parameters.extend(cusips)
        if figis:
            conditions.append(f"figi IN ({','.join('?' for _ in figis)})")
            parameters.extend(figis)
        if not conditions:
            connection.close()
            return InstitutionalQueryResult(
                state="identifier_mapping_required",
                report_period=selected_period,
                holders=[],
                total=0,
                institution_count=0,
                total_shares=None,
                security_identifiers=[],
                security_classes=[],
                mapping_method=None,
                mapping_confidence=None,
                warnings=["The verified mapping has no usable CUSIP or FIGI."],
            )
        where = " OR ".join(conditions)
        # Only the number of SQL placeholders and the fixed "OR" operator are
        # assembled here. Every identifier remains a bound parameter.
        query = """
            WITH deduped_positions AS (
                SELECT manager_cik, MAX(manager_name) AS manager_name,
                       COALESCE(cusip, figi) AS security_identifier,
                       MAX(cusip) AS cusip, MAX(figi) AS figi,
                       MAX(class_title) AS class_title, shares_held,
                       reported_value_usd, investment_discretion,
                       MAX(filing_date) AS filing_date,
                       MAX(accession_number) AS accession_number,
                       MAX(source_url) AS source_url
                FROM holdings
                WHERE report_period = ? AND COALESCE(put_call, '') = ''
                  AND (__IDENTIFIER_FILTER__)
                GROUP BY manager_cik, COALESCE(cusip, figi), shares_held,
                         reported_value_usd, investment_discretion
            )
            SELECT h.manager_name, h.manager_cik, h.cusip, h.figi,
                   h.class_title, SUM(h.shares_held) AS shares_held,
                   SUM(h.reported_value_usd) AS reported_value_usd,
                   MAX(h.filing_date) AS filing_date,
                   MAX(h.accession_number) AS accession_number,
                   MAX(h.source_url) AS source_url,
                   mt.reported_value_usd AS total_value
            FROM deduped_positions h
            LEFT JOIN manager_portfolio_totals mt
              ON mt.manager_cik = h.manager_cik
             AND mt.report_period = ?
            GROUP BY h.manager_cik, h.security_identifier
            ORDER BY shares_held DESC
            """
        query = query.replace("__IDENTIFIER_FILTER__", where)  # nosec B608
        rows = connection.execute(
            query,
            [selected_period, *parameters[1:], selected_period],
        ).fetchall()
        connection.close()
    except sqlite3.DatabaseError:
        return InstitutionalQueryResult(
            state="temporarily_unavailable",
            report_period=None,
            holders=[],
            total=0,
            institution_count=0,
            total_shares=None,
            security_identifiers=[],
            security_classes=[],
            mapping_method=None,
            mapping_confidence=None,
            warnings=["The SEC Form 13F index is unavailable or incomplete."],
        )

    mapping_method = mappings[0]["mapping_method"]
    mapping_confidence = float(mappings[0]["confidence"])
    holders = []
    for row in rows[offset : offset + limit]:
        value = row["reported_value_usd"]
        total_value = row["total_value"]
        holders.append(
            {
                "institution_name": row["manager_name"],
                "manager_cik": row["manager_cik"],
                "shares_held": row["shares_held"],
                "reported_value_usd": value,
                "ownership_percent": None,
                "portfolio_weight_percent": (
                    value / total_value * 100
                    if value is not None and total_value
                    else None
                ),
                "report_period": selected_period,
                "filing_date": row["filing_date"],
                "accession_number": row["accession_number"],
                "source_url": row["source_url"],
                "cusip": row["cusip"],
                "figi": row["figi"],
                "class_title": row["class_title"],
                "mapping_method": mapping_method,
                "mapping_confidence": mapping_confidence,
            }
        )
    warnings = [
        "Based on SEC Form 13F filings; filings may be submitted after quarter "
        "end and do not represent all investors.",
        "Options were excluded from common-share ownership totals.",
    ]
    if mapping_confidence < 1:
        warnings.append(
            "Security mapping uses a high-confidence issuer-name match and "
            "should be reviewed if multiple share classes exist."
        )
    return InstitutionalQueryResult(
        state="available" if rows else "unavailable",
        report_period=selected_period,
        holders=holders,
        total=len(rows),
        institution_count=len({row["manager_cik"] for row in rows}),
        total_shares=(
            sum(int(row["shares_held"]) for row in rows)
            if rows and all(row["shares_held"] is not None for row in rows)
            else None
        ),
        security_identifiers=sorted(
            {
                str(row["cusip"] or row["figi"])
                for row in rows
                if row["cusip"] or row["figi"]
            }
        ),
        security_classes=sorted(
            {
                str(row["class_title"])
                for row in mappings
                if row["class_title"]
            }
        ),
        mapping_method=mapping_method,
        mapping_confidence=mapping_confidence,
        warnings=warnings,
    )
