from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.providers.sec import SEC_TICKERS_URL
from app.providers.sec_13f import (
    SEC_13F_ARCHIVE_BASE,
    discover_latest_archive_url,
    download_archive,
    import_13f_archive,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the latest official SEC Form 13F quarterly dataset."
    )
    parser.add_argument("--archive-url")
    parser.add_argument("--archive-path")
    args = parser.parse_args()
    settings = get_settings()
    archive_url = args.archive_url
    if args.archive_path:
        archive_path = args.archive_path
        if not archive_url:
            archive_url = (
                f"{SEC_13F_ARCHIVE_BASE}{Path(archive_path).name}"
            )
    else:
        archive_url = archive_url or discover_latest_archive_url(
            settings.sec_user_agent,
            settings.provider_timeout_seconds,
        )
        archive_path = download_archive(
            archive_url,
            settings.sec_13f_cache_dir,
            settings.sec_user_agent,
        )
    ticker_response = httpx.get(
        SEC_TICKERS_URL,
        headers={"User-Agent": settings.sec_user_agent},
        timeout=settings.provider_timeout_seconds,
    )
    ticker_response.raise_for_status()
    stats = import_13f_archive(
        archive_path,
        settings.sec_13f_database_path,
        source_url=archive_url,
        mapping_file=settings.sec_13f_mapping_file,
        ticker_rows=ticker_response.json().values(),
    )
    print(json.dumps(stats.__dict__, indent=2))


if __name__ == "__main__":
    main()
