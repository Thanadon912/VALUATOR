import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE_URL = process.env.VALUATION_SMOKE_BASE_URL || "http://127.0.0.1:3200";
const API_BASE_URL = process.env.VALUATION_SMOKE_API_BASE_URL || "";
const API_URL = API_BASE_URL || BASE_URL;
const TICKERS = (process.env.VALUATION_SMOKE_TICKERS || "AAPL,TSLA,AMZN")
  .split(",")
  .map((ticker) => ticker.trim().toUpperCase())
  .filter(Boolean);

const ENGINE_HEADINGS = [
  "Asset-Based Valuation",
  "Discounted Cash Flow (DCF)",
  "Dividend Discount Model (DDM)",
  "Relative Valuation",
  "Residual Income Model (RI)",
];

const DISALLOWED_NAV = [
  "Financials",
  "Statistics",
  "Capital Allocation",
  "Profile",
  "Holders",
  "Chart",
  "Conversations",
  "Historical Data",
  "Analysis",
  "Options",
];

function isExpectedConsoleNoise(message) {
  const text = message.text();
  return (
    message.type() === "warning" ||
    text.includes("React DevTools") ||
    text.includes("[HMR]") ||
    text.includes("/_next/webpack-hmr") ||
    text.includes("img.logo.dev")
  );
}

async function readBody(page) {
  return page.locator("body").innerText();
}

async function expectNoBrokenFinancialText(page) {
  const text = await readBody(page);
  assert.doesNotMatch(text, /\bNaN\b/i, "UI must not render NaN");
  assert.doesNotMatch(text, /\bInfinity\b/i, "UI must not render Infinity");
  assert.doesNotMatch(text, />null<|\bnull\b/i, "UI must not leak null values");
  assert.doesNotMatch(text, /Engine Failure|API error 5\d\d/i, "Valuation API failures must not surface");
}

async function assertWorkspaceNavigation(page) {
  await assertVisible(page, "link", "Summary");
  await assertVisible(page, "link", "News");
  await assertVisible(page, "link", "Valuation");

  for (const label of DISALLOWED_NAV) {
    assert.equal(
      await page.getByRole("link", { name: new RegExp(`^${label}$`, "i") }).count(),
      0,
      `${label} tab must not be present`,
    );
  }
  assert.equal(
    await page.getByRole("link", { name: /^Related Tickers$/i }).count(),
    0,
    "Related Tickers tab must not be present",
  );
}

async function assertTelemetryHeader(page, ticker) {
  await page.waitForFunction(
    () =>
      /MKT CAP/i.test(document.body.innerText) &&
      /BETA/i.test(document.body.innerText) &&
      /Risk-Free \(10Y\)/i.test(document.body.innerText) &&
      /Cost of Equity/i.test(document.body.innerText),
    null,
    { timeout: 30_000 },
  );
  const text = await readBody(page);

  for (const label of ["MKT CAP", "BETA", "Risk-Free (10Y)", "Cost of Equity"]) {
    const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    assert.match(text, new RegExp(escapedLabel, "i"), `${ticker} header includes ${label}`);
  }
  assert.doesNotMatch(
    text,
    /MKT CAP\s+N\/A|BETA\s+N\/A|Risk-Free \(10Y\)\s+N\/A|Cost of Equity\s+N\/A/i,
    `${ticker} header telemetry must not render N/A`,
  );
}

async function assertVisible(page, role, name) {
  await page.getByRole(role, { name }).first().waitFor({ state: "visible", timeout: 30_000 });
}

async function assertEngineSurface(page, ticker) {
  await page.goto(`${BASE_URL}/stocks/${ticker}/valuation`, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });

  await page.waitForFunction(
    () => document.body.innerText.includes("Valuation Overview"),
    null,
    { timeout: 30_000 },
  );

  await assertWorkspaceNavigation(page);
  await assertVisible(page, "heading", `${ticker} valuation dashboard`);
  await assertVisible(page, "tab", "Valuation Overview");
  await assertVisible(page, "tab", "DCF Intrinsic Deep-Dive");

  const overview = page.getByRole("tab", { name: "Valuation Overview" });
  await overview.click();
  await assertVisible(page, "heading", "Compare valuation methods");

  await page.waitForFunction(
    (headings) => headings.every((heading) => document.body.innerText.includes(heading)),
    ENGINE_HEADINGS,
    { timeout: 30_000 },
  );

  for (const heading of ENGINE_HEADINGS) {
    assert.match(await readBody(page), new RegExp(heading.replace(/[()]/g, "\\$&")), `${heading} is visible`);
  }

  const text = await readBody(page);
  const missingCount = (text.match(/Missing Inputs/g) || []).length;
  assert.ok(missingCount < ENGINE_HEADINGS.length, `${ticker} should not show Missing Inputs for every valuation engine`);
  assert.match(
    text,
    /Fair Value|Blended Fair Value|Intrinsic|Value \$|Missing Inputs/i,
    `${ticker} overview must expose valuation output or explicit missing-input state`,
  );
  await assertTelemetryHeader(page, ticker);

  if (await page.locator("table").filter({ hasText: "Peer Ticker" }).count()) {
    const firstPeerCheckbox = page
      .locator("table")
      .filter({ hasText: "Peer Ticker" })
      .locator('input[type="checkbox"]')
      .first();
    if (await firstPeerCheckbox.count()) {
      await firstPeerCheckbox.uncheck();
      assert.match(await readBody(page), /Blended Fair Value/, "Relative valuation remains usable after peer toggle");
      await firstPeerCheckbox.check();
    }
  }

  await expectNoBrokenFinancialText(page);
}

async function assertDcfDeepDive(page, ticker) {
  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).click();
  await page.waitForTimeout(250);

  const text = await readBody(page);
  if (text.includes("DCF Intrinsic Deep-Dive") && text.includes("Missing Inputs")) {
    assert.match(
      text,
      /Not calculated\. Required sourced inputs are missing:/,
      `${ticker} DCF missing state must explain missing sourced inputs`,
    );
    await expectNoBrokenFinancialText(page);
    return;
  }

  await page.waitForFunction(
    () =>
      (document.body.innerText.includes("WACC Architecture") ||
        document.body.innerText.includes("Discount Rate Architecture")) &&
      (document.body.innerText.includes("FCF & Margin Trajectory") || 
       document.body.innerText.includes("Fundamental Trajectory")) &&
      /\d+-Year Projection Array/.test(document.body.innerText) &&
      document.body.innerText.includes("WACC Sensitivity Matrix"),
    null,
    { timeout: 30_000 },
  );

  const text_body = await readBody(page);
  assert.ok(
    /FCF & Margin Trajectory|Fundamental Trajectory/.test(text_body),
    `${ticker} DCF deep-dive includes trajectory chart`
  );
  
  for (const label of ["Projection Array", "WACC Sensitivity Matrix"]) {
    assert.match(text_body, new RegExp(label), `${ticker} DCF deep-dive includes ${label}`);
  }
  assert.match(
    await readBody(page),
    /WACC Architecture|Discount Rate Architecture/,
    `${ticker} DCF deep-dive includes the discount-rate architecture`,
  );

  for (const scenario of ["Bear Case", "Base Case", "Bull Case"]) {
    await assertVisible(page, "radio", scenario);
  }

  const sensitivityBaseCell = page.getByTestId("sensitivity-base-cell");
  const sensitivityBaseValue = await sensitivityBaseCell.innerText();
  assert.match(await readBody(page), /Base-case sensitivity · center matches the Overview DCF/i, "Sensitivity matrix identifies its base-case basis");
  await page.getByRole("radio", { name: "Bear Case" }).click();
  assert.equal(await sensitivityBaseCell.innerText(), sensitivityBaseValue, "Bear projection does not relabel the base sensitivity");
  await page.getByRole("radio", { name: "Bull Case" }).click();
  assert.equal(await sensitivityBaseCell.innerText(), sensitivityBaseValue, "Bull projection does not relabel the base sensitivity");
  await page.getByRole("radio", { name: "Base Case" }).click();
  assert.equal(await sensitivityBaseCell.innerText(), sensitivityBaseValue, "Base sensitivity center remains stable");
  assert.ok(
    await page.getByRole("region", { name: "Sensitivity matrix" }).locator("tbody tr").count() > 0,
    `${ticker} sensitivity matrix must render backend rows`,
  );

  await expectNoBrokenFinancialText(page);
}

async function assertMarketRealitySurface(page, ticker) {
  const response = await fetch(`${API_URL}/api/v1/valuation/dcf?ticker=${ticker}`, {
    headers: { accept: "application/json" },
  });
  assert.equal(response.ok, true, `${ticker} DCF API must respond for market reality check`);
  const payload = await response.json();
  const growth = payload.implied_expectations?.implied_stage_1_revenue_cagr
    ?? payload.implied_expectations?.implied_revenue_cagr;
  if (payload.valuation_status !== "CALCULATED" || !Number.isFinite(growth)) return;

  await page.getByRole("tab", { name: "Valuation Overview" }).click();
  await page.getByText("Market Reality Check", { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
  assert.match(
    await readBody(page),
    new RegExp(`${(growth * 100).toFixed(1)}% Revenue CAGR`),
    `${ticker} overview must show solved implied growth without clipping`,
  );

  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  if (payload.monte_carlo_results?.iteration_count != null) {
    await page.getByText(/valid outcomes from 10,000 runs/i).waitFor({ state: "visible", timeout: 30_000 });
  } else {
    await page.getByText("No simulation percentiles were returned", { exact: true }).waitFor({
      state: "visible",
      timeout: 30_000,
    });
    assert.match(
      await readBody(page),
      /Monte Carlo unavailable: insufficient comparable annual history/,
      `${ticker} simulation surface must disclose insufficient historical volatility inputs`,
    );
  }
  await page.getByText("Required Stage-1 Revenue Growth", { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
  assert.match(
    await readBody(page),
    new RegExp((growth * 100).toFixed(1)),
    `${ticker} reverse DCF surface must retain solved growth`,
  );
}

async function assertDcfApiSanity(ticker) {
  const response = await fetch(`${API_URL}/api/v1/valuation/dcf?ticker=${ticker}`, {
    headers: { accept: "application/json" },
  });
  assert.equal(response.ok, true, `${ticker} DCF API must respond successfully`);

  const payload = await response.json();
  if (payload.valuation_status !== "CALCULATED") {
    assert.match(
      payload.underlying_assumptions?.calculation_basis || "",
      /missing|invalid|validation/i,
      `${ticker} non-calculated DCF must explain its input state`,
    );
    return;
  }

  const assumptions = payload.underlying_assumptions || {};
  const projections = payload.projections || assumptions.projections || [];
  const methodology = payload.valuation_methodology;
  assert.equal(Number.isFinite(payload.computed_fair_value), true, `${ticker} DCF fair value must be finite`);
  assert.equal(typeof methodology, "string", `${ticker} DCF must expose valuation_methodology`);
  assert.equal(typeof payload.engine_metadata, "object", `${ticker} DCF must expose engine_metadata`);
  assert.ok(projections.length >= 1, `${ticker} DCF must expose standardized projection rows`);
  if (payload.monte_carlo_results?.iteration_count != null) {
    assert.equal(payload.monte_carlo_results.iteration_count, 10_000, `${ticker} Monte Carlo must run 10,000 iterations`);
    assert.ok(payload.monte_carlo_results.histogram_bins?.length > 0, `${ticker} Monte Carlo must expose histogram bins`);
  } else {
    assert.match(
      (assumptions.computational_warnings || []).join(" "),
      /Monte Carlo unavailable: insufficient comparable annual history/,
      `${ticker} unavailable Monte Carlo must disclose insufficient historical volatility inputs`,
    );
  }
  assert.ok(payload.forward_dcf?.sensitivity_matrix?.length > 0, `${ticker} DCF must expose sensitivity rows`);
  const sensitivityMatrix = payload.forward_dcf.sensitivity_matrix;
  const centerRow = sensitivityMatrix[Math.floor(sensitivityMatrix.length / 2)];
  const centerCell = centerRow?.cells?.[Math.floor((centerRow.cells?.length || 0) / 2)];
  assert.equal(Number.isFinite(centerCell?.fair_value), true, `${ticker} sensitivity center must be finite`);
  assert.ok(
    Math.abs(centerCell.fair_value - payload.computed_fair_value) < 0.01,
    `${ticker} sensitivity center must match the Overview DCF`,
  );
  assert.equal(payload.forward_dcf.sensitivity_basis?.scenario, "base", `${ticker} sensitivity basis must be base case`);

  for (const row of projections) {
    assert.equal(Number.isFinite(row.year), true, `${ticker} projection row must expose finite year`);
    assert.equal(typeof row.capital_deduction_label, "string", `${ticker} projection row must expose a deduction label`);
    assert.equal(
      Number.isFinite(row.capital_deduction_value),
      true,
      `${ticker} projection row must expose finite deduction value`,
    );
  }

  if (methodology === "Regulatory FCFE") {
    assert.equal(
      payload.engine_metadata.discount_rate_type,
      "Cost of Equity (Ke)",
      `${ticker} FCFE engine must state Cost of Equity discounting`,
    );
    assert.equal(assumptions.wacc_used, false, `${ticker} FCFE engine must not use WACC`);
    assert.equal(
      projections.every((row) => Number.isFinite(row.net_income) && Number.isFinite(row.free_cash_flow_to_equity)),
      true,
      `${ticker} FCFE projections must expose net income and FCFE`,
    );
    assert.equal(
      projections.every((row) => row.capital_deduction_label === "Required Regulatory Capital"),
      true,
      `${ticker} FCFE projections must label required regulatory capital`,
    );
  } else {
    if (payload.engine_metadata?.model_version === "growth_multistage_fcff_v3") {
      assert.equal(
        assumptions.discount_rate_basis,
        "current_wacc_fading_to_mature_wacc",
        `${ticker} growth DCF must fade current WACC to mature WACC`,
      );
      assert.equal(
        assumptions.wacc_basis,
        "true_wacc_market_cap_debt_interest_tax",
        `${ticker} growth DCF must retain market-value WACC telemetry`,
      );
    } else {
      assert.equal(
        assumptions.discount_rate_basis || assumptions.wacc_basis,
        "true_wacc",
        `${ticker} non-financial DCF must use true WACC discounting`,
      );
    }
    assert.equal(
      projections.every((row) => Number.isFinite(row.revenue) && Number.isFinite(row.unlevered_free_cash_flow)),
      true,
      `${ticker} driver DCF projections must expose revenue and unlevered FCF`,
    );
    assert.equal(
      projections.every((row) => row.capital_deduction_label === "Reinvestment"),
      true,
      `${ticker} driver DCF projections must label reinvestment`,
    );
  }

  if (ticker === "TSLA" && payload.engine_metadata?.model_version === "growth_multistage_fcff_v3") {
    assert.equal(projections.length, 15, "TSLA growth DCF must expose its 15-year horizon");
    assert.equal(
      payload.implied_expectations?.implied_projection_horizon_years,
      15,
      "TSLA reverse DCF must expose the same 15-year horizon",
    );
  }
}

async function assertAssetBasedApiSanity(ticker) {
  const response = await fetch(`${API_URL}/api/v1/valuation/asset-based?ticker=${ticker}`, {
    headers: { accept: "application/json" },
  });
  assert.equal(response.ok, true, `${ticker} asset-based API must respond successfully`);

  const payload = await response.json();
  if (payload.valuation_status !== "CALCULATED") {
    assert.match(
      payload.underlying_assumptions?.calculation_basis || "",
      /missing|invalid|validation/i,
      `${ticker} non-calculated asset-based valuation must explain its input state`,
    );
    return;
  }

  const assumptions = payload.underlying_assumptions || {};
  for (const key of [
    "total_assets",
    "total_liabilities",
    "goodwill",
    "intangible_assets",
    "standard_nav_per_share",
    "tangible_net_net_per_share",
  ]) {
    assert.equal(Number.isFinite(assumptions[key]), true, `${ticker} asset-based ${key} must be finite`);
  }

  if (ticker === "TSLA") {
    assert.ok(
      assumptions.intangible_assets > 0,
      "TSLA asset-based valuation must source SEC intangible assets instead of rendering Missing Inputs",
    );
  }
  if (ticker === "AMZN") {
    assert.ok(
      assumptions.total_liabilities > 0,
      "AMZN asset-based valuation must derive total liabilities when SEC reports assets and stockholders' equity but no Liabilities fact",
    );
    assert.match(
      assumptions.total_liabilities_basis,
      /derived_from_total_assets_minus_stockholders_equity|reported_total_liabilities/,
      "AMZN total liabilities basis must be explicit",
    );
  }
  if (ticker === "TSM") {
    assert.ok(
      assumptions.goodwill > 0 && assumptions.intangible_assets > 0,
      "TSM asset deductions must reject the latest vendor zero placeholders",
    );
    assert.ok(
      assumptions.standard_nav_per_share > assumptions.tangible_net_net_per_share,
      "TSM tangible NAV must deduct sourced goodwill and intangible assets from book value",
    );
  }
}

async function assertRelativeApiSanity(ticker) {
  const response = await fetch(`${API_URL}/api/v1/valuation/relative?ticker=${ticker}`, {
    headers: { accept: "application/json" },
  });
  assert.equal(response.ok, true, `${ticker} relative API must respond successfully`);

  const payload = await response.json();
  if (payload.valuation_status !== "CALCULATED") {
    assert.match(
      payload.underlying_assumptions?.calculation_basis || "",
      /missing|invalid|validation/i,
      `${ticker} non-calculated relative valuation must explain its input state`,
    );
    return;
  }

  const assumptions = payload.underlying_assumptions || {};
  const peers = assumptions.peers || [];
  assert.ok(peers.length > 0, `${ticker} relative valuation must expose peer metrics`);

  for (const peer of peers) {
    assert.notEqual(peer.pe, 0, `${ticker} ${peer.symbol} P/E must not use 0 as a missing-value placeholder`);
    assert.notEqual(
      peer.ev_ebitda,
      0,
      `${ticker} ${peer.symbol} EV/EBITDA must not use 0 as a missing-value placeholder`,
    );
  }

  if (ticker === "TSLA") {
    const byd = peers.find((peer) => peer.symbol === "BYD");
    assert.ok(byd, "TSLA relative valuation must include BYD as a peer");
    assert.ok(byd.pe > 0, "BYD P/E must be sourced or derived");
    assert.ok(byd.ev_ebitda > 0, "BYD EV/EBITDA must be sourced or derived");
  }
}

const browser = await chromium.launch({ headless: true });
const failures = [];

try {
  for (const ticker of TICKERS) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const consoleProblems = [];
    const failedValuationResponses = [];
    const proxiedValuationRequests = [];
    const proxyErrors = [];

    page.on("console", (message) => {
      if (!isExpectedConsoleNoise(message)) {
        consoleProblems.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => {
      consoleProblems.push(`pageerror: ${error.message}`);
    });
    page.on("response", (response) => {
      const url = response.url();
      if (url.includes("/api/v1/valuation/") && response.status() >= 500) {
        failedValuationResponses.push(`${response.status()} ${url}`);
      }
    });

    if (API_BASE_URL) {
      await page.route("**/api/v1/valuation/**", async (route) => {
        try {
          const requestUrl = new URL(route.request().url());
          const upstreamUrl = `${API_BASE_URL}${requestUrl.pathname}${requestUrl.search}`;
          proxiedValuationRequests.push(upstreamUrl);
          const upstream = await fetch(upstreamUrl, {
            headers: { accept: "application/json" },
          });
          await route.fulfill({
            status: upstream.status,
            headers: { "content-type": upstream.headers.get("content-type") || "application/json" },
            body: await upstream.text(),
          });
        } catch (error) {
          proxyErrors.push(error instanceof Error ? error.message : String(error));
          await route.abort("failed");
        }
      });
    }

    try {
      await assertAssetBasedApiSanity(ticker);
      await assertDcfApiSanity(ticker);
      await assertRelativeApiSanity(ticker);
      await assertEngineSurface(page, ticker);
      await assertMarketRealitySurface(page, ticker);
      await assertDcfDeepDive(page, ticker);
      assert.deepEqual(failedValuationResponses, [], `${ticker} valuation endpoints must not return 5xx`);
      assert.deepEqual(consoleProblems, [], `${ticker} page must not log runtime errors`);
      console.log(`[valuation-smoke] ${ticker} passed`);
    } catch (error) {
      const diagnostic = [
        `${ticker}: ${error.message}`,
        proxiedValuationRequests.length ? `proxied=${proxiedValuationRequests.length}` : "proxied=0",
        proxyErrors.length ? `proxyErrors=${proxyErrors.join(" | ")}` : "",
        failedValuationResponses.length ? `valuation5xx=${failedValuationResponses.join(" | ")}` : "",
        consoleProblems.length ? `console=${consoleProblems.join(" | ")}` : "",
      ].filter(Boolean).join(" ");
      failures.push(diagnostic);
      await page.screenshot({
        path: `/tmp/valuation-smoke-${ticker}.png`,
        fullPage: true,
      });
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}

if (failures.length > 0) {
  throw new Error(`Valuation production smoke failed:\n${failures.join("\n")}`);
}
