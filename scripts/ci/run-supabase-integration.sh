#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cli_version="${SUPABASE_CLI_VERSION:-2.112.0}"
test_image="${SUPABASE_TEST_IMAGE:?SUPABASE_TEST_IMAGE is required}"
reports_dir="${SUPABASE_REPORTS_DIR:-$project_root/ci-artifacts/supabase}"
npm_cache_dir="${SUPABASE_NPM_CACHE_DIR:-$project_root/.cache/supabase-cli-$cli_version}"
lock_file="${SUPABASE_CI_LOCK_FILE:-${TMPDIR:-/tmp}/valuator-supabase-ci-$(id -u).lock}"
ci_workdir="${SUPABASE_CI_WORKDIR:-$project_root/.cache/supabase-ci-project}"

mkdir -p "$npm_cache_dir"

# Supabase local uses fixed ports and Docker resource names from config.toml.
# Multibranch jobs are separate Jenkins jobs, so disableConcurrentBuilds does
# not serialize them. Hold a host-wide lock until the EXIT cleanup completes.
exec 9>"$lock_file"
flock --wait 300 9

supabase_cli() {
  # Jenkins can run branch/PR jobs concurrently. A workspace-local npm cache
  # prevents both jobs from replacing the shared npx binary while it executes.
  npm_config_cache="$npm_cache_dir" npx --yes "supabase@$cli_version" \
    --workdir "$ci_workdir" "$@"
}

cleanup() {
  supabase_cli stop --project-id valuator_ci --no-backup >/dev/null 2>&1 || true
}
trap cleanup EXIT

# The deterministic integration suite does not call Google, but GoTrue needs
# values to render the enabled local provider configuration.
export GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-ci-google-client-id}"
export GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-ci-google-client-secret}"

cd "$project_root"
mkdir -p "$reports_dir"

# Keep destructive integration resets away from the persistent local staging
# stack (ports 54320-54322, project_id=valuator). The copied project uses its
# own Docker resources and host ports while sharing the tracked migrations.
rm -rf "$ci_workdir/supabase"
mkdir -p "$ci_workdir/supabase"
cp "$project_root/supabase/config.toml" "$ci_workdir/supabase/config.toml"
cp -R "$project_root/supabase/migrations" "$ci_workdir/supabase/migrations"
sed -i \
  -e 's/project_id = "valuator"/project_id = "valuator_ci"/' \
  -e 's/port = 54321/port = 55321/' \
  -e 's/port = 54322/port = 55322/' \
  -e 's/shadow_port = 54320/shadow_port = 55320/' \
  "$ci_workdir/supabase/config.toml"

# An aborted Jenkins run can leave the isolated project registered while one of
# its containers is already stopped. The host-wide lock is held here, so it is
# safe to clear only this CI project before creating the next clean instance.
supabase_cli stop --project-id valuator_ci --no-backup >/dev/null 2>&1 || true
supabase_cli start --exclude edge-runtime,imgproxy,logflare,mailpit,postgres-meta,realtime,storage-api,studio,supavisor,vector >/dev/null
supabase_cli db reset

status_env="$(supabase_cli status -o env)"
while IFS='=' read -r key value; do
  value="${value#\"}"
  value="${value%\"}"
  case "$key" in
    API_URL) supabase_url="$value" ;;
    PUBLISHABLE_KEY) publishable_key="$value" ;;
    SECRET_KEY) secret_key="$value" ;;
    ANON_KEY) legacy_anon_key="$value" ;;
    SERVICE_ROLE_KEY) legacy_service_role_key="$value" ;;
  esac
done <<< "$status_env"
unset status_env

publishable_key="${publishable_key:-${legacy_anon_key:-}}"
secret_key="${secret_key:-${legacy_service_role_key:-}}"

: "${supabase_url:?Supabase CLI did not return API_URL}"
: "${publishable_key:?Supabase CLI did not return ANON_KEY}"
: "${secret_key:?Supabase CLI did not return SERVICE_ROLE_KEY}"

docker run --rm --network host \
  -e SUPABASE_INTEGRATION_TEST=true \
  -e SUPABASE_URL="$supabase_url" \
  -e SUPABASE_PUBLISHABLE_KEY="$publishable_key" \
  -e SUPABASE_SECRET_KEY="$secret_key" \
  -v "$reports_dir:/reports" \
  "$test_image" \
  python -m pytest tests/test_supabase_integration.py \
    --junitxml=/reports/supabase-junit.xml \
    --alluredir=/reports/allure-results \
    --allure-no-capture
