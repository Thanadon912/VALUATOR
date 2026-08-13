#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cli_version="${SUPABASE_CLI_VERSION:-2.112.0}"
workdir="${PERF_SUPABASE_WORKDIR:-/tmp/valuator-performance-supabase}"
env_file="${PERF_SUPABASE_ENV_FILE:-/tmp/valuator-performance-supabase.env}"
project_id="valuator_perf"

supabase_cli() {
  npx --yes "supabase@$cli_version" --workdir "$workdir" "$@"
}

write_runtime_env() {
  local status_env api_url publishable_key secret_key db_url legacy_anon legacy_service_role
  status_env="$(supabase_cli status -o env)"
  while IFS='=' read -r key value; do
    value="${value#\"}"
    value="${value%\"}"
    case "$key" in
      API_URL) api_url="$value" ;;
      PUBLISHABLE_KEY) publishable_key="$value" ;;
      SECRET_KEY) secret_key="$value" ;;
      ANON_KEY) legacy_anon="$value" ;;
      SERVICE_ROLE_KEY) legacy_service_role="$value" ;;
      DB_URL) db_url="$value" ;;
    esac
  done <<< "$status_env"
  unset status_env
  publishable_key="${publishable_key:-${legacy_anon:-}}"
  secret_key="${secret_key:-${legacy_service_role:-}}"
  : "${api_url:?Supabase CLI did not return API_URL}"
  : "${publishable_key:?Supabase CLI did not return a publishable key}"
  : "${secret_key:?Supabase CLI did not return a secret key}"
  : "${db_url:?Supabase CLI did not return DB_URL}"
  umask 077
  {
    printf 'SUPABASE_URL=%s\n' "$api_url"
    printf 'SUPABASE_PUBLISHABLE_KEY=%s\n' "$publishable_key"
    printf 'SUPABASE_SECRET_KEY=%s\n' "$secret_key"
    printf 'PERF_POSTGRES_DSN=%s\n' "$db_url"
  } > "$env_file"
  printf '%s\n' "$env_file"
}

start() {
  export GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-perf-google-client-id}"
  export GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-perf-google-client-secret}"
  rm -rf "$workdir/supabase"
  mkdir -p "$workdir/supabase"
  cp "$project_root/supabase/config.toml" "$workdir/supabase/config.toml"
  cp -R "$project_root/supabase/migrations" "$workdir/supabase/migrations"
  sed -i \
    -e "s/project_id = \"valuator\"/project_id = \"$project_id\"/" \
    -e 's/port = 54321/port = 56321/' \
    -e 's/port = 54322/port = 56322/' \
    -e 's/shadow_port = 54320/shadow_port = 56320/' \
    "$workdir/supabase/config.toml"
  supabase_cli start --exclude edge-runtime,imgproxy,logflare,mailpit,postgres-meta,realtime,storage-api,studio,supavisor,vector >/dev/null
  supabase_cli db reset >/dev/null
  write_runtime_env
}

stop() {
  supabase_cli stop --project-id "$project_id" --no-backup >/dev/null 2>&1 || true
  rm -f "$env_file"
}

case "${1:-}" in
  start) start ;;
  status) write_runtime_env ;;
  stop) stop ;;
  *) printf 'Usage: %s {start|status|stop}\n' "$0" >&2; exit 2 ;;
esac
