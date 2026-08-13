from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


SUPPLY_CHAIN_EXTRACTOR_VERSION = "supply-chain-v1"
_cache_lock = Lock()


def _cache_key(ticker: str, accessions: tuple[str, ...]) -> str:
    value = "|".join(
        (SUPPLY_CHAIN_EXTRACTOR_VERSION, ticker, *accessions)
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cache_path(
    cache_dir: str | Path,
    ticker: str,
    accessions: tuple[str, ...],
) -> Path:
    return Path(cache_dir) / f"{ticker}-{_cache_key(ticker, accessions)}.json"


def _valid_payload(
    payload: Any,
    ticker: str,
    accessions: tuple[str, ...],
) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ticker") != ticker:
        return False
    if payload.get("extractor_version") != SUPPLY_CHAIN_EXTRACTOR_VERSION:
        return False
    if tuple(payload.get("accessions") or []) != accessions:
        return False
    result = payload.get("result")
    return bool(
        isinstance(result, dict)
        and isinstance(result.get("supply_chain_exposure"), dict)
        and isinstance(result.get("extraction"), dict)
        and result["extraction"].get("method") == "ai"
    )


def load_supply_chain_cache(
    cache_dir: str | Path,
    ticker: str,
    accessions: tuple[str, ...],
) -> dict[str, Any] | None:
    path = _cache_path(cache_dir, ticker, accessions)
    try:
        with _cache_lock:
            payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not _valid_payload(payload, ticker, accessions):
        return None
    result = deepcopy(payload["result"])
    result["extraction"]["cache_source"] = "persistent"
    result["extraction"]["extractor_version"] = (
        SUPPLY_CHAIN_EXTRACTOR_VERSION
    )
    return result


def save_supply_chain_cache(
    cache_dir: str | Path,
    ticker: str,
    accessions: tuple[str, ...],
    result: dict[str, Any],
) -> None:
    path = _cache_path(cache_dir, ticker, accessions)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    payload = {
        "ticker": ticker,
        "accessions": list(accessions),
        "extractor_version": SUPPLY_CHAIN_EXTRACTOR_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }
    try:
        with _cache_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
