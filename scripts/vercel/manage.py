#!/usr/bin/env python3
"""Bootstrap and deploy the Git-connected Vercel projects.

The script never uploads a local working tree. Every deployment is created
from the exact GitHub commit SHA that Jenkins has already tested.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API = "https://api.vercel.com"
REPOSITORY = "Thanadon912/VALUATOR"
FRONTEND_PROJECT = "valuator-thanadon912"
BACKEND_PROJECT = "valuator-api-thanadon912"
FRONTEND_URL = f"https://{FRONTEND_PROJECT}.vercel.app"
BACKEND_URL = f"https://{BACKEND_PROJECT}.vercel.app"

PROJECTS = {
    BACKEND_PROJECT: {"rootDirectory": "Back-End", "framework": None},
    FRONTEND_PROJECT: {"rootDirectory": "Front-End", "framework": "nextjs"},
}

PUBLIC_ENV_KEYS = {
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "GOOGLE_AUTH_ENABLED",
    "ENABLE_LIVE_PROVIDERS",
    "PERFORMANCE_CACHE_ONLY_ENABLED",
    "SUPABASE_TIMEOUT_SECONDS",
    "PROVIDER_TIMEOUT_SECONDS",
    "SUPPLY_CHAIN_AI_ENABLED",
    "CUSTOMER_MIX_AI_ENABLED",
    "EMAIL_DELIVERY_MODE",
    "EMAIL_PROVIDER",
    "SMTP_HOST",
    "SMTP_PORT",
    "EMAIL_FROM_NAME",
    "SMTP_TIMEOUT_SECONDS",
    "RESEND_FROM_EMAIL",
    "RESEND_TEST_RECIPIENT",
    "RESEND_REPLY_TO",
    "RESEND_TIMEOUT_SECONDS",
    "SEC_USER_AGENT",
}

FRONTEND_KEYS = {
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "GOOGLE_AUTH_ENABLED",
    "GEMINI_API_KEY",
    "EMAIL_INTERNAL_API_TOKEN",
    "NEXT_PUBLIC_LOGO_DEV_TOKEN",
}

BACKEND_KEYS = {
    "ENABLE_LIVE_PROVIDERS",
    "PERFORMANCE_CACHE_ONLY_ENABLED",
    "SEC_USER_AGENT",
    "PROVIDER_TIMEOUT_SECONDS",
    "FRED_API_KEY",
    "FMP_API_KEY",
    "FINNHUB_API_KEY",
    "GEMINI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_API_SECRET",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_TIMEOUT_SECONDS",
    "SUPPLY_CHAIN_AI_ENABLED",
    "CUSTOMER_MIX_AI_ENABLED",
    "EMAIL_DELIVERY_MODE",
    "EMAIL_PROVIDER",
    "EMAIL_INTERNAL_API_TOKEN",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "EMAIL_FROM",
    "EMAIL_FROM_NAME",
    "EMAIL_REPLY_TO",
    "SMTP_TIMEOUT_SECONDS",
    "RESEND_API_KEY",
    "RESEND_FROM_EMAIL",
    "RESEND_TEST_RECIPIENT",
    "RESEND_REPLY_TO",
    "RESEND_TIMEOUT_SECONDS",
}


class VercelError(RuntimeError):
    pass


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | list[Any] | None = None,
) -> Any:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except HTTPError as exc:
        try:
            detail = json.load(exc).get("error", {}).get("message", "request failed")
        except Exception:
            detail = "request failed"
        raise VercelError(f"Vercel API {method} {path} failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise VercelError(f"Vercel API is unreachable: {exc.reason}") from exc


def get_project(token: str, name: str) -> dict[str, Any] | None:
    try:
        return api_request(token, "GET", f"/v9/projects/{quote(name)}")
    except VercelError as exc:
        if "(404)" in str(exc):
            return None
        raise


def upsert_project(token: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    project = get_project(token, name)
    create_payload = {
        "name": name,
        "rootDirectory": spec["rootDirectory"],
        "gitRepository": {"type": "github", "repo": REPOSITORY},
    }
    if spec["framework"] is not None:
        create_payload["framework"] = spec["framework"]
    if project is None:
        api_request(token, "POST", "/v10/projects", create_payload)
        print(f"Created Git-connected Vercel project {name}")
    updates = {
        "rootDirectory": spec["rootDirectory"],
        "autoAssignCustomDomains": False,
    }
    if spec["framework"] is not None:
        updates["framework"] = spec["framework"]
    project = api_request(
        token,
        "PATCH",
        f"/v9/projects/{quote(name)}",
        updates,
    )
    if project is not None:
        print(f"Verified Vercel project {name}")
    link = project.get("link") or {}
    if link.get("type") != "github" or link.get("org") != "Thanadon912" or link.get("repo") != "VALUATOR":
        raise VercelError(f"{name} is not linked to the approved GitHub repository")
    if project.get("rootDirectory") != spec["rootDirectory"]:
        raise VercelError(f"{name} has an unexpected root directory")
    if project.get("autoAssignCustomDomains") is not False:
        raise VercelError(f"{name} must disable automatic production domain assignment")
    return project


def env_payload(key: str, value: str) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "type": "plain" if key in PUBLIC_ENV_KEYS or key.startswith("NEXT_PUBLIC_") else "sensitive",
        "target": ["production", "preview"],
    }


def replace_environment(token: str, project: str, values: dict[str, str]) -> None:
    current = api_request(token, "GET", f"/v9/projects/{quote(project)}/env").get("envs", [])
    managed_keys = set(values)
    for item in current:
        if item.get("key") in managed_keys:
            api_request(
                token,
                "DELETE",
                f"/v9/projects/{quote(project)}/env/{quote(item['id'])}",
            )
    payload = [env_payload(key, value) for key, value in sorted(values.items()) if value]
    if payload:
        api_request(token, "POST", f"/v10/projects/{quote(project)}/env", payload)
    print(f"Configured {len(payload)} managed environment variables for {project}")


def runtime_values(project: str, supplied: dict[str, str]) -> dict[str, str]:
    if project == FRONTEND_PROJECT:
        values = {key: supplied.get(key, "") for key in FRONTEND_KEYS}
        values.update(
            {
                "API_BASE_URL": BACKEND_URL,
                "APP_BASE_URL": FRONTEND_URL,
                "APP_ENV": "production",
                "GOOGLE_AUTH_ENABLED": "false",
            }
        )
        return values
    values = {key: supplied.get(key, "") for key in BACKEND_KEYS}
    provider = supplied.get("EMAIL_PROVIDER", "").strip().lower()
    delivery_mode = supplied.get("EMAIL_DELIVERY_MODE", "").strip().lower()
    if not delivery_mode:
        delivery_mode = "smtp" if provider in {"gmail_smtp", "smtp"} else "disabled"
    values.update(
        {
            "APP_BASE_URL": FRONTEND_URL,
            "CORS_ALLOWED_ORIGINS": FRONTEND_URL,
            "GOOGLE_AUTH_ENABLED": "false",
            "ENABLE_LIVE_PROVIDERS": supplied.get("ENABLE_LIVE_PROVIDERS", "true"),
            "PERFORMANCE_CACHE_ONLY_ENABLED": supplied.get(
                "PERFORMANCE_CACHE_ONLY_ENABLED", "false"
            ),
            "EMAIL_DELIVERY_MODE": delivery_mode,
        }
    )
    return values


def bootstrap(token: str, env_file: Path) -> None:
    supplied = read_env(env_file)
    required = {
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "EMAIL_INTERNAL_API_TOKEN",
    }
    provider = supplied.get("EMAIL_PROVIDER", "").strip().lower()
    delivery_mode = supplied.get("EMAIL_DELIVERY_MODE", "").strip().lower()
    if delivery_mode == "smtp" or provider in {"gmail_smtp", "smtp"}:
        required.update(
            {"SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"}
        )
    elif delivery_mode in {"resend", "resend_test"} or provider.startswith("resend"):
        required.add("RESEND_API_KEY")
        if delivery_mode == "resend_test" or provider == "resend_test":
            required.add("RESEND_TEST_RECIPIENT")
    else:
        raise VercelError("Production EMAIL_PROVIDER or EMAIL_DELIVERY_MODE is invalid")
    missing = sorted(key for key in required if not supplied.get(key))
    if missing:
        raise VercelError(f"Production environment file is missing: {', '.join(missing)}")
    for name, spec in PROJECTS.items():
        upsert_project(token, name, spec)
        replace_environment(token, name, runtime_values(name, supplied))


def create_deployment(token: str, project: dict[str, Any], revision: str) -> dict[str, Any]:
    link = project["link"]
    payload = {
        "name": project["name"],
        "target": "production",
        "gitSource": {
            "type": "github",
            "repoId": link["repoId"],
            "ref": "main",
            "sha": revision,
        },
        "meta": {"jenkinsGated": "true", "testedCommitSha": revision},
    }
    return api_request(
        token,
        "POST",
        "/v13/deployments?forceNew=1&skipAutoDetectionConfirmation=1",
        payload,
    )


def wait_ready(token: str, deployment_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        deployment = api_request(token, "GET", f"/v13/deployments/{quote(deployment_id)}")
        state = deployment.get("readyState")
        if state == "READY":
            return deployment
        if state in {"ERROR", "CANCELED"}:
            raise VercelError(f"Deployment {deployment_id} ended in state {state}")
        time.sleep(5)
    raise VercelError(f"Deployment {deployment_id} did not become ready within 10 minutes")


def http_json(url: str) -> Any:
    try:
        with urlopen(Request(url, headers={"User-Agent": "VALUATOR-Jenkins-Smoke/1.0"}), timeout=30) as response:
            if response.status != 200:
                raise VercelError(f"Smoke endpoint returned HTTP {response.status}: {url}")
            return json.load(response)
    except (HTTPError, URLError, ValueError) as exc:
        raise VercelError(f"Smoke request failed for {url}") from exc


def wait_for_payload(url: str, predicate, description: str) -> Any:
    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = http_json(url)
            if predicate(payload):
                return payload
        except VercelError as exc:
            last_error = exc
        time.sleep(3)
    suffix = f": {last_error}" if last_error else ""
    raise VercelError(f"Timed out waiting for {description}{suffix}")


def deploy(token: str, revision: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise VercelError("REVISION must be a full 40-character Git SHA")
    projects = {name: upsert_project(token, name, spec) for name, spec in PROJECTS.items()}
    backend = wait_ready(token, create_deployment(token, projects[BACKEND_PROJECT], revision)["id"])
    frontend = wait_ready(token, create_deployment(token, projects[FRONTEND_PROJECT], revision)["id"])
    backend_preview = f"https://{backend['url']}"
    frontend_preview = f"https://{frontend['url']}"
    backend_sso = (projects[BACKEND_PROJECT].get("ssoProtection") or {}).get(
        "deploymentType"
    ) == "all_except_custom_domains"
    frontend_sso = (projects[FRONTEND_PROJECT].get("ssoProtection") or {}).get(
        "deploymentType"
    ) == "all_except_custom_domains"
    if backend_sso:
        print("Backend staged content smoke deferred because the deployment URL requires Vercel SSO")
    elif http_json(f"{backend_preview}/health") != {"status": "ok"}:
        raise VercelError("Backend staged health payload is invalid")
    if frontend_sso:
        print("Frontend staged content smoke deferred because the deployment URL requires Vercel SSO")
    else:
        release = http_json(f"{frontend_preview}/api/release")
        if release.get("revision") != revision:
            raise VercelError("Frontend staged deployment does not match the tested SHA")
    for name, deployment in ((BACKEND_PROJECT, backend), (FRONTEND_PROJECT, frontend)):
        project_id = projects[name].get("id")
        if not isinstance(project_id, str) or not project_id:
            raise VercelError(f"Vercel project {name} did not include an id")
        api_request(
            token,
            "POST",
            f"/v10/projects/{quote(project_id)}/promote/{quote(deployment['id'])}",
            {},
        )
        print(f"Promoted {name} deployment {deployment['id']}")
    wait_for_payload(
        f"{BACKEND_URL}/health",
        lambda payload: payload == {"status": "ok"},
        "production backend health",
    )
    wait_for_payload(
        f"{FRONTEND_URL}/api/release",
        lambda payload: isinstance(payload, dict)
        and payload.get("revision") == revision,
        "production frontend SHA",
    )
    print(f"Production verified at {FRONTEND_URL} (SHA {revision})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("bootstrap", "deploy"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--revision")
    args = parser.parse_args()
    token = (
        os.environ.get("VERCEL_TOKEN")
        or os.environ.get("VERCEL_ACCESS_TOKEN")
        or os.environ.get("VERCEL_API_KEY")
        or ""
    ).strip()
    if not token:
        raise VercelError("VERCEL_TOKEN is required")
    if args.command == "bootstrap":
        if args.env_file is None:
            raise VercelError("--env-file is required for bootstrap")
        bootstrap(token, args.env_file)
    else:
        if not args.revision:
            raise VercelError("--revision is required for deploy")
        deploy(token, args.revision)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VercelError as exc:
        print(f"vercel deployment error: {exc}", file=sys.stderr)
        raise SystemExit(1)
