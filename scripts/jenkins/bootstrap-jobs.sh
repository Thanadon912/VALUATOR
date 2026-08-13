#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="${JENKINS_ENV_FILE:-$project_root/.env.jenkins}"
runtime_env_file="${VALUATOR_RUNTIME_ENV_FILE:-$project_root/.env}"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing Jenkins environment file: %s\n' "$env_file" >&2
  exit 1
fi

if [[ ! -f "$runtime_env_file" ]]; then
  printf 'Missing VALUATOR runtime environment file: %s\n' "$runtime_env_file" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

# A one-shot override is useful for local controllers whose public and agent URLs differ.
JENKINS_URL="${JENKINS_URL_OVERRIDE:-${JENKINS_URL:-}}"
case "$JENKINS_URL" in
  https://localhost:8080*|https://127.0.0.1:8080*)
    JENKINS_URL="http://${JENKINS_URL#https://}"
    ;;
esac

: "${JENKINS_URL:?JENKINS_URL is required}"
: "${JENKINS_USERNAME:?JENKINS_USERNAME is required}"
: "${JENKINS_API_TOKEN:?JENKINS_API_TOKEN is required}"

JENKINS_URL="${JENKINS_URL%/}"
ci_job="${JENKINS_CI_JOB:-valuator-ci}"
live_job="${JENKINS_LIVE_JOB:-valuator-live-e2e}"

for name in "$ci_job" "$live_job"; do
  if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf 'Unsafe Jenkins job name: %s\n' "$name" >&2
    exit 1
  fi
done

auth=(--user "$JENKINS_USERNAME:$JENKINS_API_TOKEN")
curl_common=(--silent --show-error --fail-with-body "${auth[@]}")
plugins_json="$(mktemp)"
trap 'rm -f "$plugins_json"' EXIT

curl "${curl_common[@]}" "$JENKINS_URL/api/json" >/dev/null
curl "${curl_common[@]}" "$JENKINS_URL/pluginManager/api/json?depth=1" -o "$plugins_json"

python3 - "$plugins_json" <<'PY'
import json
import sys

required = {
    "credentials-binding",
    "git",
    "github-branch-source",
    "junit",
    "pipeline-model-definition",
    "plain-credentials",
    "workflow-multibranch",
}
with open(sys.argv[1], encoding="utf-8") as handle:
    installed = {plugin["shortName"] for plugin in json.load(handle).get("plugins", []) if plugin.get("active")}
missing = sorted(required - installed)
if missing:
    raise SystemExit("Missing or inactive Jenkins plugins: " + ", ".join(missing))
PY

credential_response="$(curl "${curl_common[@]}" -X POST \
  --data-urlencode "script@$project_root/scripts/jenkins/ensure-github-scan-credential.groovy" \
  "$JENKINS_URL/scriptText")"
if [[ "$credential_response" != *"GitHub scan credential"* ]]; then
  printf '%s\n' "$credential_response" >&2
  exit 1
fi

runtime_env_base64="$(base64 < "$runtime_env_file" | tr -d '\n')"
vercel_token_base64="$(python3 - "$project_root" "$runtime_env_file" <<'PY'
import base64
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from scripts.vercel.manage import read_env

values = read_env(Path(sys.argv[2]))
token = (
    values.get("VERCEL_TOKEN")
    or values.get("VERCEL_ACCESS_TOKEN")
    or values.get("VERCEL_API_KEY")
)
if not token:
    raise SystemExit("Runtime environment is missing a Vercel access token")
print(base64.b64encode(token.encode()).decode(), end="")
PY
)"
runtime_credential_script="$(sed \
  -e "s|__VALUATOR_RUNTIME_ENV_BASE64__|$runtime_env_base64|" \
  -e "s|__VERCEL_TOKEN_BASE64__|$vercel_token_base64|" \
  "$project_root/scripts/jenkins/ensure-runtime-env-credential.groovy.template")"
unset runtime_env_base64
unset vercel_token_base64
runtime_credential_response="$(curl "${curl_common[@]}" -X POST \
  --data-urlencode "script=$runtime_credential_script" \
  "$JENKINS_URL/scriptText")"
unset runtime_credential_script
if [[ "$runtime_credential_response" != *"Jenkins production credentials are ready"* ]]; then
  printf '%s\n' "$runtime_credential_response" >&2
  exit 1
fi

validate_jenkinsfile() {
  local path="$1"
  local response
  response="$(curl "${curl_common[@]}" -X POST -F "jenkinsfile=<$path" "$JENKINS_URL/pipeline-model-converter/validate")"
  if [[ "$response" != *"successfully validated"* ]]; then
    printf '%s\n' "$response" >&2
    return 1
  fi
}

upsert_job() {
  local name="$1"
  local config="$2"
  local status
  status="$(curl --silent --output /dev/null --write-out '%{http_code}' "${auth[@]}" "$JENKINS_URL/job/$name/api/json")"
  if [[ "$status" == "200" ]]; then
    curl "${curl_common[@]}" -X POST -H 'Content-Type: application/xml' --data-binary "@$config" \
      "$JENKINS_URL/job/$name/config.xml" >/dev/null
    printf 'Updated Jenkins job: %s\n' "$name"
  elif [[ "$status" == "404" ]]; then
    curl "${curl_common[@]}" -X POST -H 'Content-Type: application/xml' --data-binary "@$config" \
      "$JENKINS_URL/createItem?name=$name" >/dev/null
    printf 'Created Jenkins job: %s\n' "$name"
  else
    printf 'Unable to inspect Jenkins job %s (HTTP %s).\n' "$name" "$status" >&2
    return 1
  fi
}

validate_jenkinsfile "$project_root/Jenkinsfile"
validate_jenkinsfile "$project_root/Jenkinsfile.live"
upsert_job "$ci_job" "$project_root/ops/jenkins/valuator-ci.xml"
upsert_job "$live_job" "$project_root/ops/jenkins/valuator-live-e2e.xml"

curl "${curl_common[@]}" -X POST "$JENKINS_URL/job/$ci_job/build" >/dev/null
printf 'Triggered multibranch indexing for %s.\n' "$ci_job"
