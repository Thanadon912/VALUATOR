#!/usr/bin/env bash
set -euo pipefail

: "${VERCEL_TOKEN:?VERCEL_TOKEN must be provided by the Jenkins credential}"
: "${VALUATOR_PRODUCTION_ENV:?VALUATOR_PRODUCTION_ENV must point to a Jenkins Secret File credential}"
: "${REVISION:?REVISION is required}"

python3 scripts/supabase/apply-production.py \
  --env-file "$VALUATOR_PRODUCTION_ENV" \
  --app-url "https://valuator-thanadon912.vercel.app"
python3 scripts/vercel/manage.py bootstrap --env-file "$VALUATOR_PRODUCTION_ENV"
python3 scripts/vercel/manage.py deploy --revision "$REVISION"
