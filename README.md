# VALUATOR

[![CI](https://github.com/Thanadon912/VALUATOR/actions/workflows/ci.yml/badge.svg)](https://github.com/Thanadon912/VALUATOR/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-B7FF3C.svg)](LICENSE)
[![Live demo](https://img.shields.io/badge/Live_demo-Vercel-000000.svg)](https://valuator-thanadon912.vercel.app)

Open-source portfolio project · [Live demo](https://valuator-thanadon912.vercel.app)

VALUATOR is a fair-value engine for **U.S.-listed stocks** and machine-readable
financial workflows. It combines sourced market and filing data with five
independent valuation methods, explicit calculation telemetry, probabilistic
DCF analysis, and market-implied expectations.

> [!IMPORTANT]
> VALUATOR is an educational portfolio project, not financial advice. Provider
> data may be delayed, incomplete, or unavailable. Verify source filings and
> assumptions independently before making an investment decision.

## Supported market scope

VALUATOR currently supports securities listed on U.S. exchanges and quoted in
U.S. dollars. This includes U.S.-listed ADRs or other foreign issuers when the
required provider and filing data is available. Direct listings on non-U.S.
exchanges, non-USD markets, and arbitrary global tickers are outside the current
product scope; they should be reported as unavailable rather than inferred.

The product has three stock views:

1. **Summary** — sourced quote, fundamentals, company context, and evidence.
2. **News** — current company news and sentiment signals.
3. **Valuation** — five valuation engines, DCF projections, Monte Carlo, and
   Reverse DCF.

Account features are optional. Guests can use the analysis views and keep saved
stocks or valuation assumptions locally. Configured Supabase authentication adds
cross-device persistence without becoming a prerequisite for valuation.

## Valuation engines

| Engine | Purpose | Endpoint |
|---|---|---|
| Asset-Based | NAV and tangible liquidation floor | `/api/v1/valuation/asset-based` |
| Adaptive DCF | Future cash generation discounted to present value | `/api/v1/valuation/dcf` |
| Dividend Discount Model | Gordon-growth value of distributions | `/api/v1/valuation/ddm` |
| Relative | Peer median P/E, P/B, and EV/EBITDA context | `/api/v1/valuation/relative` |
| Residual Income | Book value plus discounted residual earnings | `/api/v1/valuation/residual-income` |

The DCF endpoint routes by sector/SIC to Standard Driver-Based DCF,
Capitalized R&D DCF, Regulatory FCFE, Normalized Median DCF, or the 15-year
Growth Multi-Stage FCFF model. Its analytical layers are:

- **Monte Carlo:** exactly 10,000 runs over the active routed engine. Responses
  expose `bear_p10`, `base_p50`, `bull_p90`, iteration and valid-sample counts,
  seed, distribution, histogram bins, and live-price percentile. Insufficient
  comparable history returns an empty result plus a computational warning; the
  system never fabricates volatility.
- **Reverse DCF:** solves the stage-1 revenue CAGR and target EBIT margin needed
  to reconcile the model with a live or requested price. It also exposes the
  terminal trajectory and year-N revenue, EBIT margin, FCFF, and horizon. An
  infeasible target returns an empty result with a machine-readable warning.

All five endpoints return the common `ValuationResponse` contract:
`ticker`, `timestamp`, `current_price`, `computed_fair_value`,
`valuation_status`, `margin_of_safety_percentage`, `valuation_methodology`,
`engine_metadata`, `projections`, `monte_carlo_results`,
`implied_expectations`, and `underlying_assumptions`.

Supporting endpoints include:

- `/api/v1/valuation/inputs`
- `/api/v1/valuation/methodology`
- `/api/stocks/{ticker}/quote`
- `/api/stocks/{ticker}/summary`
- `/api/stocks/{ticker}/news`
- `/api/stocks/snapshots`
- `/api/workspace/{ticker}`
- `/health`

Example:

```bash
curl 'http://127.0.0.1:8200/api/v1/valuation/dcf?ticker=TSLA'
```

## Architecture

- **Frontend:** Next.js 16 and React in `Front-End/`, using Tailwind CSS,
  shadcn/ui, Framer Motion, and Recharts.
- **Backend:** FastAPI, Pydantic, and NumPy in `Back-End/`. Primary sources and
  providers include SEC EDGAR, U.S. Treasury/Fiscal Data, Nasdaq, Finnhub, FMP,
  and optional Gemini-assisted extraction.
- **Optional persistence:** Supabase Postgres stores provider/news cache entries,
  saved stocks, and valuation assumptions. Supabase Auth supports email/password
  and optional Google OAuth. Missing or unavailable Supabase configuration does
  not block core market-data or valuation routes.
- **CI:** GitHub Actions and Jenkins run the same Docker-backed backend,
  frontend, Supabase RLS, and deterministic browser regression gates. Jenkins
  additionally owns production deployment and scheduled live-provider checks.
  Pull requests must pass the GitHub Docker regression; after merge, Jenkins
  reruns the full regression on `main` before promoting that exact commit to
  Vercel production.

## Configuration

Copy `.env.example` to `.env` and set only the providers you intend to use.
Never commit an environment file.

Core configuration:

```dotenv
ENABLE_LIVE_PROVIDERS=true
SEC_USER_AGENT=USAStockAnalysis contact@example.com
FRONTEND_PORT=3200
BACKEND_PORT=8200
APP_BASE_URL=http://127.0.0.1:3200
```

Market-data and AI credentials such as `FMP_API_KEY`, `FINNHUB_API_KEY`,
`FRED_API_KEY`, `ALPACA_API_KEY`, and `GEMINI_API_KEY` are provider-specific and
optional. Missing source inputs produce explicit unavailable states rather than
placeholder financial data.

### Optional Supabase

Leave these values blank to run the core application without Supabase:

```dotenv
SUPABASE_URL=
SUPABASE_SECRET_KEY=
SUPABASE_PUBLISHABLE_KEY=
GOOGLE_AUTH_ENABLED=false
```

When enabled, `SUPABASE_SECRET_KEY` is backend-only. The frontend receives only
`SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`; never expose the secret through a
`NEXT_PUBLIC_*` variable, browser bundle, screenshot, or log.

To run the local Supabase feature stack:

```bash
export GOOGLE_CLIENT_ID=local-google-client-id
export GOOGLE_CLIENT_SECRET=local-google-client-secret
npx --yes supabase@2.112.0 start
npx --yes supabase@2.112.0 db reset
```

For hosted authentication, set the Site URL to `APP_BASE_URL`, allow only the
application callback/confirmation/password-update routes, configure SMTP, and
enable `GOOGLE_AUTH_ENABLED=true` only after the hosted Google provider works.

## Run locally

Backend:

```bash
cd Back-End
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8200
```

Frontend, in another terminal:

```bash
cd Front-End
cp .env.example .env.local
npm install
npm run dev -- --hostname 127.0.0.1 --port 3200
```

Open `http://127.0.0.1:3200`; backend health is
`http://127.0.0.1:8200/health`. If the backend uses another origin, set
`API_BASE_URL` before building or starting the frontend.

Docker Compose starts the same canonical port pair:

```bash
docker compose up --build
```

Override host ports without changing internal service addresses:

```bash
FRONTEND_PORT=3201 BACKEND_PORT=8201 \
APP_BASE_URL=http://127.0.0.1:3201 docker compose up --build
```

## Verification and reporting

Required source gates:

```bash
cd Front-End
npm run lint
npm run build

cd ../Back-End
.venv/bin/python -m pytest tests
```

Deterministic frontend regression runs 46 logical Playwright cases in Chromium,
Firefox, and WebKit (138 browser executions):

```bash
cd Front-End
npm run test:e2e
```

The repository currently contains 34 backend pytest files, 7 Playwright specs,
6 standalone frontend smoke scripts, and 9 k6 scenario scripts. CI derives
expected JUnit and Allure counts from each run instead of relying on a fixed
global count.

The optional Supabase schema/RLS suite uses an isolated local project and must
never target staging or production:

```bash
docker build --target test -t valuator-backend-test:local Back-End
SUPABASE_TEST_IMAGE=valuator-backend-test:local \
  scripts/ci/run-supabase-integration.sh
```

Raw reporting locations are:

- frontend: `ci-artifacts/allure-results`
- backend: `ci-artifacts/backend/allure-results`
- Supabase: `ci-artifacts/supabase/allure-results`
- combined publication input: `ci-artifacts/allure-combined-results`
- Playwright HTML/JUnit: `ci-artifacts/playwright`

Validate and assemble current results with:

```bash
node scripts/ci/validate-allure-results.mjs
node scripts/ci/assemble-allure-results.mjs
```

JUnit remains the quality gate; Allure is reporting only. Passing tests must not
attach logs, screenshots, traces, tokens, cookies, or payloads. Failed frontend
tests retain screenshots/traces only; video stays disabled.

## Performance testing

Performance tests are restricted to the dedicated loopback stack. Never run
stress, spike, or soak profiles against production, shared staging, public
providers, or a real user database. Measured requests use
`X-VALUATOR-Cache-Only: true`; one bounded sequential warm-up is the only phase
allowed to contact providers.

Static preflight:

```bash
bash -n run_all_perf_tests.sh scripts/performance/manage-isolated-supabase.sh
PERF_POSTGRES_DSN=postgresql://placeholder@127.0.0.1:56322/postgres \
  docker compose -f docker-compose-perf.yml config --quiet
jq empty grafana/dashboards/valuator-custom-dashboard.json
for script in k6-tests/tests/*.js; do
  docker run --rm -v "$PWD/k6-tests:/scripts:ro" \
    grafana/k6:2.1.0 inspect "/scripts/tests/$(basename "$script")"
done
```

Execution requires an ignored backend environment file:

```bash
PERF_TARGET_ACK=local-dedicated \
PERF_BACKEND_ENV_FILE=/absolute/path/to/project/.env \
  ./run_all_perf_tests.sh smoke    # cold/warm contract and smoke

PERF_TARGET_ACK=local-dedicated \
PERF_BACKEND_ENV_FILE=/absolute/path/to/project/.env \
  ./run_all_perf_tests.sh baseline # smoke + three baselines + focused profiles

PERF_TARGET_ACK=local-dedicated \
PERF_BACKEND_ENV_FILE=/absolute/path/to/project/.env \
  ./run_all_perf_tests.sh full     # stress, spike, recovery, and 30-minute soak
```

Correctness must remain 100%, warm HTTP failures below 1%, Monte Carlo timeouts
and invalid valuations at zero. Provisional local p95 gates are 250 ms for
health, 1 s for quote/methodology/auth, 2 s for summary/news, 3 s for snapshots,
5 s for non-DCF valuation engines, and 20 s for DCF with 10,000 simulations.

## Troubleshooting

| Symptom | Verify | Safe fix |
|---|---|---|
| Frontend returns proxy 500/connection refused | Confirm backend `/health`, `API_BASE_URL`, and ports 3200/8200 | Restart the intended backend or rebuild frontend with the correct internal API origin |
| Auth/sync says unavailable | Check all required Supabase values for that tier; core APIs should remain healthy | Leave Supabase blank for guest mode or configure URL plus the correct frontend/backend key; never substitute mock credentials |
| Supabase cache warning | Check backend URL/secret and PostgREST reachability | Restore the optional cache or continue provider-direct with the explicit warning |
| Docker uses stale containers | Run `docker compose ps` and inspect the exact project name | Use `docker compose down --volumes --remove-orphans` only for the isolated local/test project |
| Supabase CI project is half-running | Check for stopped `supabase_db_valuator_ci`; do not target `valuator` staging | Rerun the isolated script, which locks and cleans only the CI project |
| Allure/JUnit count mismatch | Compare each suite's current JUnit count with its own `*-result.json` files | Remove stale generated results and rerun the affected producer; never hard-code a global count |
| Duplicate Allure trend entries | Inspect `widgets/history-trend.json` by build order | Publish only the collision-checked combined directory once |
| Artifact permission denied | Inspect numeric ownership under `ci-artifacts` | Run a scoped container `chown` on `ci-artifacts`; never use `chmod -R 777` |
| Passing tests contain attachments | Inspect attachment names/types without printing payloads | Disable capture at the producer and keep Playwright evidence failure-only |
| CI provenance is `local`/`uncommitted` | Inspect allowlisted `environment.properties` | Pass the real `CI_BRANCH` and `CI_COMMIT`; never relax the provenance gate |
| Performance cache miss during measurement | Confirm warm-up/probe order and cache-only header | Stop the run, recreate only the dedicated performance backend, warm sequentially, and retry |
| Turbopack build cannot bind an internal worker port | Confirm the failure is an OS/sandbox permission error | Rerun the same production build in an environment that permits the worker port; do not change application code |

For any artifact secret-pattern match, record only the file and pattern category,
remove environment dumps/full payloads, rotate any exposed credential, and block
the merge until the scan is clean.

## Documentation

- [Product rules and architecture](AGENTS.md)
- [Valuation calculation source of truth](docs/valuation-calculations.md)
- [Product principles](docs/product.md)
- [Design system](docs/design.md)
- [Vercel deployment gate](docs/vercel-deployment.md)

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md)
before starting, and report vulnerabilities privately using
[SECURITY.md](SECURITY.md) rather than opening a public issue.

## License

Released under the [MIT License](LICENSE). Source code may be used, modified,
and redistributed under its terms. API keys, tokens, provider credentials,
production data, and third-party data licenses are not included.
