#!/usr/bin/env python3
"""Apply the approved auth-email migrations through Supabase Management API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


API = "https://api.supabase.com"
USER_AGENT = "VALUATOR production deployment/1.0"
MIGRATIONS = (
    "202608100001_create_auth_email_deliveries.sql",
    "202608100002_create_auth_email_rate_limits.sql",
)


class MigrationError(RuntimeError):
    pass


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value.strip().strip('"').strip("'")
    return values


def request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    raw = json.dumps(payload).encode() if payload is not None else None
    call = Request(
        f"{API}{path}",
        data=raw,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(call, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        raise MigrationError(f"Supabase Management API request failed ({exc.code})") from exc
    except (URLError, ValueError) as exc:
        raise MigrationError("Supabase Management API is unavailable") from exc


def project_ref(values: dict[str, str]) -> str:
    explicit = values.get("SUPABASE_PROJECT_REF", "").strip()
    if explicit:
        if not re.fullmatch(r"[a-z]{20}", explicit):
            raise MigrationError("SUPABASE_PROJECT_REF is invalid")
        return explicit
    hostname = urlsplit(values.get("SUPABASE_URL", "")).hostname or ""
    inferred = hostname.split(".", 1)[0]
    if not re.fullmatch(r"[a-z]{20}", inferred):
        raise MigrationError("Could not infer SUPABASE_PROJECT_REF from SUPABASE_URL")
    return inferred


def query(token: str, ref: str, sql: str) -> Any:
    return request(
        token,
        "POST",
        f"/v1/projects/{quote(ref)}/database/query",
        {"query": sql},
    )


def apply_migrations(token: str, ref: str, repository_root: Path) -> None:
    migration_dir = repository_root / "supabase" / "migrations"
    statements = [
        "select pg_catalog.pg_advisory_xact_lock(847215093);",
        *[(migration_dir / name).read_text(encoding="utf-8") for name in MIGRATIONS],
    ]
    query(token, ref, "begin;\n" + "\n".join(statements) + "\ncommit;")
    result = query(
        token,
        ref,
        """
        select
          to_regclass('public.auth_email_deliveries') is not null as delivery_table,
          to_regclass('public.auth_email_rate_limits') is not null as rate_limit_table,
          not has_function_privilege('anon', 'public.consume_auth_email_rate_limit(text,text,integer,integer)', 'execute') as anon_rpc_denied,
          not has_function_privilege('authenticated', 'public.consume_auth_email_rate_limit(text,text,integer,integer)', 'execute') as authenticated_rpc_denied;
        """,
    )
    if not isinstance(result, list) or len(result) != 1 or not all(result[0].values()):
        raise MigrationError("Hosted auth-email schema verification failed")
    print("Hosted Supabase auth-email schema and RLS grants verified")


def configure_auth(token: str, ref: str, app_url: str) -> None:
    path = f"/v1/projects/{quote(ref)}/config/auth"
    current = request(token, "GET", path)
    allow_list = current.get("uri_allow_list", "")
    entries = [item.strip() for item in allow_list.split(",") if item.strip()]
    callback = f"{app_url.rstrip('/')}/auth/callback"
    confirm = f"{app_url.rstrip('/')}/auth/confirm"
    for url in (callback, confirm):
        if url not in entries:
            entries.append(url)
    request(
        token,
        "PATCH",
        path,
        {
            "site_url": app_url.rstrip("/"),
            "uri_allow_list": ",".join(entries),
        },
    )
    print("Hosted Supabase site URL and redirect allow-list verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--app-url", required=True)
    args = parser.parse_args()
    values = read_env(args.env_file)
    token = values.get("SUPABASE_ACCESS_TOKEN") or os.getenv("SUPABASE_ACCESS_TOKEN", "")
    if not token:
        raise MigrationError("SUPABASE_ACCESS_TOKEN is required")
    ref = project_ref(values)
    root = Path(__file__).resolve().parents[2]
    apply_migrations(token, ref, root)
    configure_auth(token, ref, args.app_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"supabase migration error: {exc}", file=sys.stderr)
        raise SystemExit(1)
