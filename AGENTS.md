# AGENTS.md

## Purpose

This document is the implementation specification for the USA Stock Analysis
application. It records the approved product structure, design constraints,
target architecture, data rules, API boundaries, and development workflow.

Read this file before changing code or design. Do not infer missing financial
data, add unapproved pages, or copy unrelated modules into the product.

## AI Agent Working Rules

- Read the relevant current files before editing; do not rely on memory of prior
  work when the worktree is available.
- Keep changes scoped to the user's request and the product rules in this file.
- Preserve user or generated changes already present in the worktree. Never
  revert unrelated dirty files unless the user explicitly asks.
- Prefer existing project patterns, local helpers, schemas, and components over
  introducing new abstractions.
- Use real provider/API data only. If data is missing, surface a missing-input
  or unavailable state instead of fabricating fallback values.
- For frontend work, preserve the approved dark glassmorphism visual system,
  compact financial typography, and existing route structure.
- For backend valuation work, expose calculation basis, source inputs, and
  machine-readable telemetry in JSON responses.
- **CRITICAL VALUATION RULE**: Whenever you are implementing, modifying, debugging, or reviewing ANY valuation formulas or calculation logic, you MUST read and strictly adhere to `docs/valuation-calculations.md`. It is the absolute source of truth for all calculations. Do not infer or invent formulas.
- After every code change, run the required verification gates before reporting
  completion:
  - Frontend lint: `cd Front-End && npm run lint`
  - Frontend production build: `cd Front-End && npm run build`
  - Backend tests: `cd Back-End && .venv/bin/python -m pytest tests`
- If the sandbox blocks `npm run build` because Turbopack cannot bind its
  internal worker port, rerun the same build outside the sandbox and report that
  the first failure was environmental.
- When frontend behavior changes, run the relevant Playwright smoke script
  against local frontend/backend servers when practical.

## Product Overview

The application is a high-performance "Universal Fair Value Engine & AI-Ready API" 
for value investors and AI agents. It calculates absolute, relative, and asset-based 
Fair Values for any global ticker, presenting this as an interactive playground for 
human investors and a clean, predictable JSON Schema for autonomous AI Agents.

## Non-Negotiable Product Rules

- Never invent prices, financial statements, revenue segments, suppliers,
  executives, ownership positions, news, or valuation assumptions.
- Never present placeholder values as real values.
- Do not calculate valuation outputs until every required input is present and valid.
- Every provider value must retain its source and source timestamp when available.
- Every derived value must expose its calculation basis and source inputs.
- Facts, provider estimates, user assumptions, and app-derived calculations
  must be visually and structurally distinguishable.
- `Related Tickers` is excluded from every stock-analysis page.
- Keep every page scoped to the currently selected company.

## Repository Layout

- `Front-End/` - current static frontend prototype and visual assets.
- `Back-End/` - current FastAPI application, validation, placeholder provider,
  DCF calculation, and tests.
- `Design/Penpot/` - export/import artifacts and approved design references.
- `scripts/` - design-generation and project utility scripts.
- `pytest.ini` - backend test discovery and Python path configuration.
- `AGENTS.md` - product and architecture source of truth.

## Visual System

### Palette

- Use an almost-black background with a subtle green cast.
- Use very dark card surfaces rather than green-filled panels.
- Use thin, low-contrast green borders.
- Reserve vivid green for active navigation, primary actions, chart series,
  status indicators, and selected controls.
- Use amber sparingly for warning, bottleneck, or negative-value context.
- Avoid a page that reads as uniformly green.

### Typography

- Use a clean sans-serif interface font.
- Use strong white headings, muted green-gray supporting text, and compact
  labels.
- Financial tables must prioritize scanning over display typography.
- Do not scale font sizes directly with viewport width.

## Application Navigation

The platform consists of only THREE high-yield views:

1. Summary Dashboard (Consolidated real-time asset header and core overview)
2. News Dashboard (Market sentiment streaming)
3. Valuation / Fair Value Dashboard (The core product: Houses our 5 proprietary valuation engines)

Explicitly excluded:

- Financials Tab
- Statistics Tab
- Capital Allocation Tab
- Profile Tab
- Holders Tab
- Chart
- Conversations
- Historical Data
- Analysis
- Options

## Route Architecture

Target routes:

- `/` - ticker search and first-screen experience.
- `/stocks/[ticker]/summary`
- `/stocks/[ticker]/news`
- `/stocks/[ticker]/valuation`

## The 5 Specific Valuation Engines

### 1. Asset-Based Valuation (Net Asset & Liquidation Value)
- **Objective:** Evaluate the baseline rock-bottom floor price of the firm if it liquidated today.
- **Formulas:**
  - `NAV = Total Assets - Total Liabilities`
  - `Tangible NAV = NAV - Goodwill - Intangible Assets`

### 2. Discounted Cash Flow (DCF) Engine
- **Objective:** Project future cash creation over a multi-year horizon and discount it to present value.
- **Formulas:**
  - `Base Year FCF_0 = Cash Flow from Operations - Capital Expenditures`
  - `Enterprise Value = sum PV(FCF) + PV(TV)`
- **Adaptive Routing:** The `/api/v1/valuation/dcf` endpoint routes the company
  through the sector/SIC mapper and runs the selected engine:
  - `Standard Driver-Based DCF`
  - `Capitalized R&D DCF`
  - `Regulatory FCFE`
  - `Normalized Median DCF`
- **Stochastic Layer:** After the deterministic adaptive DCF completes, run a
  NumPy-backed Monte Carlo wrapper over the same selected engine. The wrapper
  must run exactly `10,000` iterations, perturb revenue growth and operating
  margin using historical volatility, and expose:
  - `bear_p10`
  - `base_p50`
  - `bull_p90`
- **Reverse Engineering Layer:** The DCF response should attempt an implied
  expectations goal-seek against the active live market price. It returns the
  revenue growth and operating/EBIT margin required to reconcile model fair
  value to the market price when the target is inside the solver's feasible
  bracket. If the market price is outside the feasible bracket, return an empty
  `implied_expectations` object and a machine-readable warning in
  `underlying_assumptions.computational_warnings`; do not fabricate a result.

### 3. Dividend Discount Model (DDM) Engine
- **Objective:** Treat the equity as a continuous perpetuity stream of cash distributions.
- **Formulas:**
  - `Fair Value per Share = (D_0 * (1 + g_div)) / (K_e - g_div)`

### 4. Relative Valuation Engine (Peer Multiples matrix)
- **Objective:** Evaluate market pricing context by contrasting target metrics against a localized peer network.
- **Formulas:** Uses Median/Average for `P/E`, `P/B`, `EV/EBITDA` against target EPS, BVPS, EBITDA.

### 5. Residual Income Model (RI) Engine
- **Objective:** Value companies that do not pay dividends and have irregular FCF, but yield strong accounting book value growth.
- **Formulas:** `Fair Value = BV_0 + sum PV(Residual Income) + PV(Terminal Value)`

## Global Common Telemetry Pipeline

- **Risk-Free Rate (R_f):** Sourced from U.S. Department of the Treasury - Fiscal Data API (10-year Treasury Note). Cached globally.
- **Cost of Equity (K_e):** `K_e = R_f + (Beta * MRP)` where MRP = 5.5%.
- **WACC:** `WACC = ((E/V) * K_e) + ((D/V) * K_d * (1 - T))`

## API Specification

Every single engine exposes an independent REST API endpoint configured for flawless JSON machine parsing:
- `/api/v1/valuation/asset-based`
- `/api/v1/valuation/dcf`
- `/api/v1/valuation/ddm`
- `/api/v1/valuation/relative`
- `/api/v1/valuation/residual-income`

All response structures implement zero HTML metadata overhead. Return a deterministic JSON payload containing:
- `ticker`
- `timestamp`
- `current_price`
- `computed_fair_value`
- `valuation_status`
- `margin_of_safety_percentage`
- `valuation_methodology`
- `engine_metadata`
- `projections`
- `monte_carlo_results`
- `implied_expectations`
- `underlying_assumptions`

The DCF endpoint is adaptive. It may route to:

- `Standard Driver-Based DCF`
- `Capitalized R&D DCF`
- `Regulatory FCFE`
- `Normalized Median DCF`

Frontend components must hydrate from the returned `valuation_methodology`,
`engine_metadata`, and standardized `projections` array. Do not reintroduce mock
sector tabs or UI-only engine switching for production valuation behavior.

For DCF responses, frontend components may also hydrate probabilistic valuation
ranges from `monte_carlo_results` and market-priced expectations from
`implied_expectations`. Treat empty `implied_expectations` as a valid unavailable
state and display the related `computational_warnings` when present.
