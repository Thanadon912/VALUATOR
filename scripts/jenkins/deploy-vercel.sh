#!/usr/bin/env bash
set -euo pipefail

: "${VERCEL_TOKEN:?VERCEL_TOKEN must be provided by the Jenkins credential}"
: "${VALUATOR_PRODUCTION_ENV:?VALUATOR_PRODUCTION_ENV must point to a Jenkins Secret File credential}"
: "${REVISION:?REVISION is required}"

if ! python3 scripts/supabase/apply-production.py \
  --env-file "$VALUATOR_PRODUCTION_ENV" \
  --app-url "https://valuator-thanadon912.vercel.app"; then
  printf 'WARNING: Supabase production migration skipped or failed (management API token expired or project unavailable). Proceeding with Vercel deployment.\n' >&2
fi
python3 scripts/vercel/manage.py bootstrap --env-file "$VALUATOR_PRODUCTION_ENV"
python3 scripts/vercel/manage.py deploy --revision "$REVISION"
