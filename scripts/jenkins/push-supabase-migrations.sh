#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cli_version="${SUPABASE_CLI_VERSION:-2.112.0}"
mode="${SUPABASE_STAGING_MODE:-hosted}"
npm_cache_dir="${SUPABASE_NPM_CACHE_DIR:-$project_root/.cache/supabase-cli-$cli_version}"

mkdir -p "$npm_cache_dir"

supabase_cli() {
  npm_config_cache="$npm_cache_dir" npx --yes "supabase@$cli_version" "$@"
}

recover_stopped_local_stack() {
  local project_id db_container db_status db_health deadline
  local -a stopped_containers

  project_id="$(sed -n 's/^project_id = "\([^"]*\)"/\1/p' supabase/config.toml | head -n 1)"
  : "${project_id:?supabase/config.toml must define project_id}"
  db_container="supabase_db_${project_id}"

  if ! docker container inspect "$db_container" >/dev/null 2>&1; then
    return 0
  fi

  db_status="$(docker inspect --format '{{.State.Status}}' "$db_container")"
  if [[ "$db_status" == "running" ]]; then
    return 0
  fi

  # The CLI can report an existing stack as "already running" after a host
  # restart even though every persistent container is stopped. Restart those
  # same containers in place so the staging volume and users are preserved.
  mapfile -t stopped_containers < <(
    docker ps -aq \
      --filter "label=com.supabase.cli.project=${project_id}" \
      --filter status=exited
  )
  if (( ${#stopped_containers[@]} == 0 )); then
    printf 'Supabase database container %s is %s and no stopped project containers were found.\n' \
      "$db_container" "$db_status" >&2
    return 1
  fi

  printf 'Recovering stopped Supabase project %s without replacing its data volume.\n' "$project_id"
  docker start "$db_container" >/dev/null

  deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    db_status="$(docker inspect --format '{{.State.Status}}' "$db_container")"
    db_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$db_container")"
    if [[ "$db_status" == "running" && "$db_health" == "healthy" ]]; then
      break
    fi
    if [[ "$db_status" == "exited" || "$db_status" == "dead" ]]; then
      printf 'Supabase database container %s failed while recovering.\n' "$db_container" >&2
      return 1
    fi
    sleep 2
  done

  if [[ "$db_health" != "healthy" ]]; then
    printf 'Supabase database container %s did not become healthy within 120 seconds.\n' "$db_container" >&2
    return 1
  fi

  for container_id in "${stopped_containers[@]}"; do
    if [[ "$container_id" != "$(docker container inspect --format '{{.Id}}' "$db_container")" ]]; then
      docker start "$container_id" >/dev/null
    fi
  done
}

cd "$project_root"

if [[ "$mode" == "local" ]]; then
  # Portfolio staging runs a persistent local Supabase stack. Unlike the CI
  # project, this command never resets or stops the database.
  if [[ -n "${VALUATOR_RUNTIME_ENV:-}" ]]; then
    while IFS='=' read -r key value; do
      case "$key" in
        GOOGLE_CLIENT_ID|GOOGLE_CLIENT_SECRET) export "$key=$value" ;;
      esac
    done < "$VALUATOR_RUNTIME_ENV"
  fi
  export GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-staging-google-client-id}"
  export GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-staging-google-client-secret}"
  recover_stopped_local_stack
  supabase_cli start --exclude edge-runtime,imgproxy,logflare,mailpit,postgres-meta,realtime,storage-api,studio,supavisor,vector >/dev/null
  supabase_cli db push --local --yes
  exit 0
fi

: "${SUPABASE_DB_URL:?SUPABASE_DB_URL must be provided for hosted staging}"
supabase_cli db push --db-url "$SUPABASE_DB_URL" --yes
