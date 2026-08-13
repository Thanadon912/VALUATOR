import assert from "node:assert/strict"
import { chromium } from "playwright"

const BASE_URL = process.env.REVERSE_DCF_SMOKE_BASE_URL || "http://127.0.0.1:3200"
const API_URL = process.env.REVERSE_DCF_SMOKE_API_URL || "http://127.0.0.1:8200"
const TICKER = (process.env.REVERSE_DCF_SMOKE_TICKER || "NVDA").toUpperCase()

const response = await fetch(`${API_URL}/api/v1/valuation/dcf?ticker=${TICKER}`)
assert.equal(response.ok, true, "DCF API must respond successfully")
const payload = await response.json()
const growth = payload.implied_expectations?.implied_stage_1_revenue_cagr
  ?? payload.implied_expectations?.implied_revenue_cagr
const margin = payload.implied_expectations?.implied_target_ebit_margin
  ?? payload.implied_expectations?.implied_operating_margin
assert.equal(payload.valuation_status, "CALCULATED")
assert.equal(Number.isFinite(growth), true, "reverse DCF must return finite growth")
assert.equal(Number.isFinite(margin), true, "reverse DCF must return finite margin")

const displayGrowth = Number(process.env.REVERSE_DCF_DISPLAY_GROWTH || 1.8)
const displayMargin = Number(process.env.REVERSE_DCF_DISPLAY_MARGIN || 0.9)
const displayPayload = {
  ...payload,
  implied_expectations: {
    ...payload.implied_expectations,
    implied_revenue_cagr: displayGrowth,
    implied_stage_1_revenue_cagr: displayGrowth,
    implied_operating_margin: displayMargin,
    implied_target_ebit_margin: displayMargin,
  },
}
const growthText = `${(displayGrowth * 100).toFixed(1)}% Revenue CAGR`
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  let interceptedDcfRequests = 0
  await page.route("**/api/v1/valuation/**", route => {
    if (!new URL(route.request().url()).pathname.endsWith("/dcf")) {
      return route.continue()
    }
    interceptedDcfRequests += 1
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(displayPayload),
    })
  })
  await page.goto(`${BASE_URL}/stocks/${TICKER}/valuation`, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  })

  await page.getByText("Market Reality Check", { exact: true }).waitFor({
    state: "visible",
    timeout: 60_000,
  })
  assert.ok(interceptedDcfRequests > 0, "UI must request DCF data through the intercepted API route")
  await page.getByText(growthText, { exact: false }).waitFor({
    state: "visible",
    timeout: 30_000,
  })

  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click()
  const solverGrowthMetric = page.getByText("Required Stage-1 Revenue Growth", { exact: true }).locator("..")
  await solverGrowthMetric.waitFor({
    state: "visible",
    timeout: 30_000,
  })
  const solverGrowthMatch = (await solverGrowthMetric.innerText()).match(/\n\s*([+-]?\d+(?:\.\d+)?)/)
  const solverGrowth = solverGrowthMatch ? Number(solverGrowthMatch[1]) : Number.NaN
  assert.ok(solverGrowth > 100, "solver must render triple-digit stage-1 growth without clamping")
} finally {
  await browser.close()
}

console.log(
  `[reverse-dcf-smoke] ${TICKER} backend ${(growth * 100).toFixed(1)}%/${(margin * 100).toFixed(1)}%; reality check retained ${(displayGrowth * 100).toFixed(1)}%/${(displayMargin * 100).toFixed(1)}%`,
)
