#!/usr/bin/env bash
set -euo pipefail

: "${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE is required}"
: "${VALUATOR_RUNTIME_ENV:?VALUATOR_RUNTIME_ENV must point to the Jenkins Secret File credential}"

project_name="${STAGING_PROJECT_NAME:-valuator-staging}"
compose_file="${COMPOSE_FILE:-docker-compose.yml}"
frontend_port="${FRONTEND_PORT:-3100}"
backend_port="${BACKEND_PORT:-8100}"
runtime_env_file="$VALUATOR_RUNTIME_ENV"

if [[ "${SUPABASE_STAGING_MODE:-hosted}" == "local" ]]; then
  status_env="$(npm_config_cache="${SUPABASE_NPM_CACHE_DIR:-$PWD/.cache/supabase-cli-${SUPABASE_CLI_VERSION:-2.112.0}}" \
    npx --yes "supabase@${SUPABASE_CLI_VERSION:-2.112.0}" status -o env)"
  while IFS='=' read -r key value; do
    value="${value#\"}"
    value="${value%\"}"
    case "$key" in
      PUBLISHABLE_KEY) publishable_key="$value" ;;
      SECRET_KEY) secret_key="$value" ;;
      ANON_KEY) legacy_anon_key="$value" ;;
      SERVICE_ROLE_KEY) legacy_service_role_key="$value" ;;
    esac
  done <<< "$status_env"
  unset status_env

  publishable_key="${publishable_key:-${legacy_anon_key:-}}"
  secret_key="${secret_key:-${legacy_service_role_key:-}}"
  : "${publishable_key:?Supabase CLI did not return a publishable key}"
  : "${secret_key:?Supabase CLI did not return a secret key}"

  existing_url="$(sed -n 's/^SUPABASE_URL=//p' "$VALUATOR_RUNTIME_ENV" | tail -1)"
  : "${existing_url:?The staging runtime credential must contain SUPABASE_URL}"
  export SUPABASE_PUBLISHABLE_KEY="$publishable_key"
  export SUPABASE_SECRET_KEY="$secret_key"
fi

compose() {
  docker compose --env-file "$runtime_env_file" -p "$project_name" -f "$compose_file" "$@"
}

service_image() {
  local service="$1"
  local container_id
  container_id="$(compose ps -q "$service" 2>/dev/null || true)"
  if [[ -n "$container_id" ]]; then
    docker inspect --format '{{.Config.Image}}' "$container_id"
  fi
}

wait_for_health() {
  local deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    local backend_id frontend_id backend_health frontend_health
    backend_id="$(compose ps -q backend 2>/dev/null || true)"
    frontend_id="$(compose ps -q frontend 2>/dev/null || true)"
    if [[ -n "$backend_id" && -n "$frontend_id" ]]; then
      backend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$backend_id")"
      frontend_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$frontend_id")"
      if [[ "$backend_health" == "healthy" && "$frontend_health" == "healthy" ]]; then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

previous_backend="$(service_image backend)"
previous_frontend="$(service_image frontend)"

export BACKEND_IMAGE FRONTEND_IMAGE FRONTEND_PORT="$frontend_port" BACKEND_PORT="$backend_port"
export INTERNAL_API_BASE_URL="http://backend:8000"
export APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:$frontend_port}"

compose up -d --no-build --remove-orphans

if wait_for_health; then
  printf 'Staging deployment is healthy: frontend=%s backend=%s\n' "$FRONTEND_IMAGE" "$BACKEND_IMAGE"
  exit 0
fi

compose logs --no-color --tail=200 || true

if [[ -n "$previous_backend" && -n "$previous_frontend" ]]; then
  printf 'Health check failed; rolling back to the previous images.\n' >&2
  export BACKEND_IMAGE="$previous_backend" FRONTEND_IMAGE="$previous_frontend"
  compose up -d --no-build --remove-orphans
  if ! wait_for_health; then
    printf 'Rollback did not become healthy within 120 seconds.\n' >&2
  fi
else
  printf 'Health check failed and no previous release was available for rollback.\n' >&2
fi

exit 1
