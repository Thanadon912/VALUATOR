#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"

base_url="${BASE_URL:-http://127.0.0.1:8200}"
target_ack="${PERF_TARGET_ACK:-local-dedicated}"
suite="${1:-full}"
results_dir="$project_root/ci-artifacts/performance"
logs_dir="$results_dir/logs"
runtime_env="${PERF_SUPABASE_ENV_FILE:-/tmp/valuator-performance-supabase.env}"
compose=(docker compose --env-file "$runtime_env" -f docker-compose-perf.yml)
stats_pid=""
scoped_containers=(
  valuator-perf-backend
  valuator-performance-revalidation-influxdb-1
  valuator-performance-revalidation-grafana-1
  valuator-performance-revalidation-telegraf-1
  valuator-performance-revalidation-telegraf-postgres-1
)

if [[ "$target_ack" != "local-dedicated" ]] || [[ ! "$base_url" =~ ^http://(127\.0\.0\.1|localhost|\[::1\]): ]]; then
  printf 'Refusing unsafe performance target: %s\n' "$base_url" >&2
  exit 2
fi
if [[ ! "$suite" =~ ^(smoke|baseline|full)$ ]]; then
  printf 'Usage: %s [smoke|baseline|full]\n' "$0" >&2
  exit 2
fi

if [[ "$results_dir" != "$project_root/ci-artifacts/performance" ]]; then
  printf 'Unexpected results directory: %s\n' "$results_dir" >&2
  exit 2
fi
rm -rf "$results_dir"
mkdir -p "$logs_dir"

cleanup() {
  local cleanup_status=$?
  trap - EXIT INT TERM
  if [[ -n "$stats_pid" ]]; then kill "$stats_pid" >/dev/null 2>&1 || true; fi
  "${compose[@]}" down --remove-orphans --volumes --timeout 30 >/dev/null 2>&1 || true
  docker rm -f "${scoped_containers[@]}" >/dev/null 2>&1 || true
  scripts/performance/manage-isolated-supabase.sh stop || true
  exit "$cleanup_status"
}
trap cleanup EXIT INT TERM

scripts/performance/manage-isolated-supabase.sh start >/dev/null
set -a
source "$runtime_env"
set +a
DOCKER_SOCKET_GID="$(docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  telegraf:1.39.1 sh -c 'stat -c %g /var/run/docker.sock')"
export DOCKER_SOCKET_GID

"${compose[@]}" up -d influxdb telegraf telegraf-postgres grafana perf-backend
for _ in {1..60}; do
  if curl -fsS "$base_url/health" >/dev/null; then break; fi
  sleep 2
done
curl -fsS "$base_url/health" >/dev/null

performance_tree_hash="$({
  find k6-tests grafana scripts/performance -type f -print0 | sort -z | xargs -0 sha256sum
  sha256sum docker-compose-perf.yml telegraf.conf telegraf-postgres.conf run_all_perf_tests.sh
} | sha256sum | cut -d' ' -f1)"

{
  printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'application_commit=%s\n' "$(git rev-parse HEAD)"
  printf 'performance_tree_hash=%s\n' "$performance_tree_hash"
  printf 'target_kind=local-dedicated\n'
  printf 'base_url_host=127.0.0.1:8200\n'
  printf 'provider_mode=bounded-live-warmup-then-cache-only\n'
  printf 'backend_workers=1\n'
  printf 'backend_cpu_limit=2.0\n'
  printf 'backend_memory_limit=2GiB\n'
  printf 'docker_socket_container_gid=%s\n' "$DOCKER_SOCKET_GID"
  printf 'ticker_dataset=AAPL,JPM,TSM\n'
  printf 'k6_image=grafana/k6:2.1.0\n'
  docker version --format 'docker_server={{.Server.Version}}'
  docker compose version --short | sed 's/^/docker_compose=/'
} > "$results_dir/environment-manifest.txt"

(
  while true; do
    printf '%s,' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}' valuator-perf-backend 2>/dev/null || printf 'valuator-perf-backend,unavailable\n'
    sleep 5
  done
) > "$results_dir/backend-docker-stats.csv" &
stats_pid=$!

run_k6() {
  local name=$1
  local script=$2
  local status
  shift 2
  printf 'Running %s\n' "$name"
  if docker run --rm --network host \
    --user "$(id -u):$(id -g)" \
    -e BASE_URL="$base_url" \
    -e PERF_TARGET_ACK="$target_ack" \
    -e PERF_SCENARIO="$name" \
    -e PERF_TEST_TYPE="$name" \
    -e K6_OUT=influxdb=http://127.0.0.1:8086/k6 \
    -e SUPABASE_URL="$SUPABASE_URL" \
    -e SUPABASE_PUBLISHABLE_KEY="$SUPABASE_PUBLISHABLE_KEY" \
    "$@" \
    -v "$project_root/k6-tests:/scripts:ro" \
    -v "$results_dir:/results" \
    grafana/k6:2.1.0 run \
      --summary-export="/results/$name.json" \
      "/scripts/tests/$script" \
      > "$logs_dir/$name.log" 2>&1; then
    status=0
  else
    status=$?
  fi
  if [[ -s "$results_dir/$name.json" ]]; then
    node scripts/performance/sanitize-k6-summary.mjs "$results_dir/$name.json"
  fi
  return "$status"
}

run_observational_k6() {
  local name=$1
  local status
  if run_k6 "$@"; then status=0; else status=$?; fi
  if [[ ! -s "$results_dir/$name.json" ]]; then
    printf '%s did not produce a k6 summary (exit %s)\n' "$name" "$status" >&2
    return "$status"
  fi
  printf '%s\n' "$status" > "$results_dir/$name.exit-status"
  printf '%s completed with k6 exit status %s; continuing to recovery verification.\n' "$name" "$status"
}

finalize_results() {
  node scripts/performance/summarize-k6-results.mjs "$results_dir" > "$results_dir/summary-index.json"
  printf 'completed_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$results_dir/environment-manifest.txt"
}

run_k6 cold-cache cold_cache_test.js
run_k6 smoke-prewarm smoke_test.js -e PERF_ALLOW_LIVE_WARMUP=true
run_k6 smoke smoke_test.js

if [[ "$suite" == "smoke" ]]; then finalize_results; exit 0; fi

run_k6 baseline-1 load_test.js
run_k6 baseline-2 load_test.js
run_k6 baseline-3 load_test.js
run_k6 multi-ticker multi_ticker_test.js
run_k6 cpu-dcf cpu_valuation_test.js
run_k6 auth-saved-stocks auth_saved_stocks_test.js

if [[ "$suite" == "baseline" ]]; then finalize_results; exit 0; fi

run_observational_k6 stress stress_test.js
run_k6 post-stress-smoke smoke_test.js
run_observational_k6 spike spike_test.js
run_k6 post-spike-smoke smoke_test.js
run_k6 soak-30m soak_test.js
run_k6 final-smoke smoke_test.js

finalize_results
printf 'Performance suite completed successfully.\n'
