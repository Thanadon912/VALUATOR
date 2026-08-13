import { expect, test, type Page } from "@playwright/test";
import { allure } from "allure-playwright";

const forbiddenNavigation = [
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
  "Related Tickers",
];

async function expectCleanFinancialText(page: Page) {
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(/\bNaN\b|\bInfinity\b|>null<|Engine Failure|API error 5\d\d/i);
}

async function openValuation(page: Page, ticker = "TSLA") {
  await page.goto(`/stocks/${ticker}/valuation`);
  await expect(page.getByRole("tab", { name: "Valuation Overview" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: `${ticker} valuation dashboard` })).toBeVisible();
}

async function labelValuationCase(id: string, story: string) {
  await allure.epic("Instrument Workspace");
  await allure.feature("Valuation Dashboard");
  await allure.story(story);
  await allure.layer("frontend-e2e");
  await allure.label("priority", "P0");
  await allure.severity("blocker");
  await allure.owner("Thanadon");
  await allure.testCaseId(id);
}

function expectRelative(actual: number, expected: number, tolerance = 1e-9) {
  const relativeError = Math.abs(actual - expected) / Math.max(1, Math.abs(expected));
  expect(relativeError).toBeLessThan(tolerance);
}

function formattedMoney(value: number) {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

test("five valuation engines match the approved formula invariants", async ({ request }) => {
  await labelValuationCase("VAL-E2E-FORMULA-P0-001", "Five-engine formula oracle");

  const asset = await (await request.get("/api/v1/valuation/asset-based?ticker=TSLA")).json();
  const assetInputs = asset.underlying_assumptions;
  const nav = assetInputs.total_assets - assetInputs.total_liabilities;
  const tangibleNav = nav - assetInputs.goodwill - assetInputs.intangible_assets;
  expectRelative(assetInputs.nav, nav);
  expectRelative(assetInputs.tangible_nav, tangibleNav);
  expectRelative(asset.computed_fair_value, tangibleNav / assetInputs.shares_outstanding);

  const dcf = await (await request.get("/api/v1/valuation/dcf?ticker=TSLA")).json();
  const dcfInputs = dcf.underlying_assumptions;
  const projectedCashFlows = dcf.projections.map((row: { unlevered_free_cash_flow: number }) => row.unlevered_free_cash_flow);
  const presentValueCashFlows = projectedCashFlows.reduce(
    (sum: number, cashFlow: number, index: number) => sum + cashFlow / Math.pow(1 + dcfInputs.discount_rate, index + 1),
    0,
  );
  const terminalValue = projectedCashFlows.at(-1)! * (1 + dcfInputs.perpetual_growth_rate)
    / (dcfInputs.discount_rate - dcfInputs.perpetual_growth_rate);
  const enterpriseValue = presentValueCashFlows
    + terminalValue / Math.pow(1 + dcfInputs.discount_rate, projectedCashFlows.length);
  const equityValue = enterpriseValue - dcfInputs.total_debt + dcfInputs.cash;
  expectRelative(dcfInputs.terminal_value, terminalValue);
  expectRelative(dcfInputs.enterprise_value, enterpriseValue);
  expectRelative(dcf.computed_fair_value, equityValue / dcfInputs.shares_outstanding);
  const wacc = dcfInputs.wacc_components;
  expectRelative(
    dcfInputs.discount_rate,
    wacc.weight_equity * wacc.cost_of_equity + wacc.weight_debt * wacc.cost_of_debt_after_tax,
  );

  const ddm = await (await request.get("/api/v1/valuation/ddm?ticker=KO")).json();
  const ddmInputs = ddm.underlying_assumptions;
  expect(ddm.valuation_status).toBe("CALCULATED");
  expectRelative(
    ddm.computed_fair_value,
    ddmInputs.annual_dividend_per_share * (1 + ddmInputs.dividend_growth_cagr)
      / (ddmInputs.cost_of_equity - ddmInputs.dividend_growth_cagr),
  );

  const relative = await (await request.get("/api/v1/valuation/relative?ticker=TSLA")).json();
  const relativeInputs = relative.underlying_assumptions;
  const relativeValues = [
    relativeInputs.avg_pe * relativeInputs.target_eps,
    relativeInputs.avg_pb * relativeInputs.target_bvps,
    (relativeInputs.avg_ev_ebitda * relativeInputs.target_ebitda
      - relativeInputs.target_debt + relativeInputs.target_cash) / relativeInputs.shares_outstanding,
  ];
  expectRelative(relativeInputs.fv_pe, relativeValues[0]);
  expectRelative(relativeInputs.fv_pb, relativeValues[1]);
  expectRelative(relativeInputs.fv_ev_ebitda, relativeValues[2]);
  expectRelative(relative.computed_fair_value, relativeValues.reduce((sum, value) => sum + value, 0) / 3);

  const residual = await (await request.get("/api/v1/valuation/residual-income?ticker=TSLA")).json();
  const residualInputs = residual.underlying_assumptions;
  expectRelative(
    residualInputs.terminal_value,
    residualInputs.residual_incomes.at(-1) * residualInputs.persistence_factor
      / (1 + residualInputs.cost_of_equity - residualInputs.persistence_factor),
  );
  expectRelative(residualInputs.total_equity_value, residualInputs.bv_0 + residualInputs.pv_future_wealth);
  expectRelative(
    residual.computed_fair_value,
    residualInputs.book_value_per_share + residualInputs.pv_future_wealth_per_share,
  );
});

test("stock workspace keeps navigation, search, and account actions available while scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openValuation(page, "TSLA");

  const appBar = page.locator(".workspace-topbar");
  const workspaceNav = page.getByRole("navigation", { name: "Stock workspace views" });
  const search = page.getByPlaceholder("Search ticker or company… (TSLA)");

  await expect(appBar).toBeVisible();
  await expect(page.locator(".sidebar")).toHaveCount(0);
  await expect(search).toBeVisible();
  await expect(appBar.getByRole("button", { name: /TSLA .*saved stocks/i })).toBeVisible();
  await expect(appBar.getByRole("link", { name: /Account|Sign in/ })).toBeVisible();
  for (const label of ["Summary", "News", "Valuation"]) {
    await expect(workspaceNav.getByRole("link", { name: label, exact: true })).toBeVisible();
  }

  await page.evaluate(() => window.scrollTo(0, 900));
  await expect.poll(async () => appBar.evaluate((element) => Math.round(element.getBoundingClientRect().top))).toBe(0);
  await expect(search).toBeVisible();

  await workspaceNav.getByRole("link", { name: "News", exact: true }).click();
  await expect(page).toHaveURL(/\/stocks\/TSLA\/news$/);
  await expect(workspaceNav.getByRole("link", { name: "News", exact: true })).toHaveAttribute("aria-current", "page");
});

test("landing search opens the selected VALUATOR workspace", async ({ page }) => {
  let validSearchResolve: () => void;
  const validSearchPromise = new Promise<void>((r) => { validSearchResolve = r; });

  let invalidSearchResolve: () => void;
  const invalidSearchPromise = new Promise<void>((r) => { invalidSearchResolve = r; });

  await page.route("**/api/search?*", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    const isValid = query?.toLowerCase().includes("tesla");
    if (isValid) {
      await validSearchPromise;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ symbol: "TSLA" }),
      });
    } else {
      await invalidSearchPromise;
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: "No matching US ticker found." }),
      });
    }
  });

  await page.goto("/");
  await page.getByLabel("Ticker or company name").fill("Tesla");
  
  const openAnalysisBtn = page.getByRole("button", { name: "Open analysis" });
  await openAnalysisBtn.click();
  
  // Verify loading state explicitly
  await expect(page.getByRole("button", { name: "Opening workspace…" })).toBeVisible();

  validSearchResolve!();

  await expect(page).toHaveURL(/\/stocks\/TSLA\/valuation$/);
  await expect(page.getByRole("link", { name: "Valuation", exact: true })).toHaveAttribute("aria-current", "page");

  // Verify data consistency in the workspace topbar
  await expect(page.getByPlaceholder("Search ticker or company… (TSLA)")).toBeVisible();

  await page.goto("/");
  await page.getByLabel("Ticker or company name").fill("not listed");
  await page.getByRole("button", { name: "Open analysis" }).click();
  
  // Verify loading state for invalid search
  await expect(page.getByRole("button", { name: "Opening workspace…" })).toBeVisible();

  invalidSearchResolve!();

  await expect(page.locator("#landing-ticker-error")).toContainText("No matching US ticker found");
  await expect(page).toHaveURL(/\/$/);
});

test("landing search preserves supported ticker punctuation and rejects invalid input", async ({ page }) => {
  const queries: string[] = [];
  await page.route("**/api/search?*", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q") ?? "";
    queries.push(query);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ symbol: query === "badresult" ? "NOT VALID" : query }),
    });
  });

  await page.goto("/");
  const input = page.getByLabel("Ticker or company name");

  await input.fill("BRK.B");
  await page.getByRole("button", { name: "Open analysis" }).click();
  await expect(page).toHaveURL(/\/stocks\/BRK\.B\/valuation$/);
  expect(queries).toContain("BRK.B");

  await page.goto("/");
  await page.getByLabel("Ticker or company name").fill("BRK-B");
  await page.getByRole("button", { name: "Open analysis" }).click();
  await expect(page).toHaveURL(/\/stocks\/BRK-B\/valuation$/);
  expect(queries).toContain("BRK-B");

  await page.goto("/");
  await page.getByRole("button", { name: "Open analysis" }).click();
  await expect(page.locator("#landing-ticker-error")).toContainText("Enter a ticker symbol or company name.");

  const requestCount = queries.length;
  await page.getByLabel("Ticker or company name").fill("BRK/B");
  await page.getByRole("button", { name: "Open analysis" }).click();
  await expect(page.locator("#landing-ticker-error")).toContainText("Use letters, numbers, spaces, periods, or hyphens only.");
  expect(queries).toHaveLength(requestCount);

  await page.getByLabel("Ticker or company name").fill("badresult");
  await page.getByRole("button", { name: "Open analysis" }).click();
  await expect(page.locator("#landing-ticker-error")).toContainText("No matching US ticker found");
  await expect(page).toHaveURL(/\/$/);
});

test("overview exposes five engines and recalculates interactive controls", async ({ page, request }) => {
  await labelValuationCase("VAL-E2E-OVERVIEW-P0-001", "Overview engine interactions");
  const residualPayload = await (await request.get("/api/v1/valuation/residual-income?ticker=TSLA")).json();
  await openValuation(page);

  for (const label of ["Summary", "News", "Valuation"]) {
    await expect(page.getByRole("link", { name: new RegExp(`^${label}`) }).first()).toBeVisible();
  }
  for (const label of forbiddenNavigation) {
    await expect(page.getByRole("link", { name: new RegExp(`^${label}$`, "i") })).toHaveCount(0);
  }

  for (const label of ["MKT CAP", "BETA", "Risk-Free (10Y)", "Cost of Equity"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  for (const heading of [
    "Asset-Based Valuation",
    "Discounted Cash Flow (DCF)",
    "Dividend Discount Model (DDM)",
    "Relative Valuation",
    "Residual Income Model (RI)",
  ]) {
    await expect(page.getByRole("heading", { name: new RegExp(`^${heading.replace(/[()]/g, "\\$&")}`) }).first()).toBeVisible();
  }

  const navPerShare = page.getByText("NAV / Share").locator("..").locator("p").nth(1);
  const bookValue = await navPerShare.innerText();
  const assetMargin = page.getByText("Margin of Safety", { exact: true }).first().locator("..").locator("span");
  const bookMargin = await assetMargin.innerText();
  await page.getByRole("button", { name: "Tangible Net-Net" }).click();
  await expect(navPerShare).not.toHaveText(bookValue);
  await expect(assetMargin).not.toHaveText(bookMargin);
  await expect(page.getByRole("button", { name: "Tangible Net-Net" })).toHaveAttribute("aria-pressed", "true");

  const fairValue = page.getByTestId("dcf-fair-value");
  const initialFairValue = await fairValue.innerText();
  await page.getByRole("button", { name: /DCF assumptions/i }).click();
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("15");
  await page.getByRole("button", { name: "Apply to workspace" }).click();
  await expect(fairValue).not.toHaveText(initialFairValue);

  const blendedValue = page.getByText("Backend Blended Fair Value").locator("..").locator("td").last();
  const initialBlend = await blendedValue.innerText();
  
  // Verify currency symbol is present on Blended Fair Value
  expect(initialBlend).toMatch(/^\$\d+/);
  
  // Verify DDM engine shows as Incompatible without crashing the aggregate
  await expect(page.getByText(/DDM not applicable/i)).toBeVisible();
  await expect(page.getByText("No sourced dividend distribution is available.", { exact: false })).toBeVisible();

  // Residual Income composition must use backend-provided per-share components.
  await expect(page.getByText(formattedMoney(residualPayload.underlying_assumptions.book_value_per_share), { exact: true })).toBeVisible();
  await expect(page.getByText(formattedMoney(residualPayload.underlying_assumptions.pv_future_wealth_per_share), { exact: true })).toBeVisible();

  const relativeResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/valuation/relative")
      && response.url().includes("included_peer=GM")
      && response.url().includes("included_peer=TM"),
  );
  await page.getByLabel("Include F in peer valuation").uncheck();
  await relativeResponse;
  await expect(blendedValue).not.toHaveText(initialBlend);
  await expect(page.getByText("2 of 3 peers included")).toBeVisible();
  await expectCleanFinancialText(page);
});

test("overview renders an applicable dividend discount model", async ({ page, request }) => {
  await labelValuationCase("VAL-E2E-OVERVIEW-P0-002", "Applicable DDM");
  const response = await request.get("/api/v1/valuation/ddm?ticker=KO");
  const payload = await response.json();

  await openValuation(page, "KO");

  await expect(page.getByText(`Value ${formattedMoney(payload.computed_fair_value)}`, { exact: true })).toBeVisible();
  await expect(page.getByText("Annual Dividend / Share", { exact: true })).toBeVisible();
  await expect(page.getByText("DDM not applicable", { exact: true })).toHaveCount(0);
  const comparisonRow = page.getByText("Dividend Discount Model", { exact: true }).first().locator("..").locator("..");
  await expect(comparisonRow.getByText("Available", { exact: true })).toBeVisible();
  await expect(comparisonRow.getByText(formattedMoney(payload.computed_fair_value), { exact: false })).toBeVisible();
});

test("residual income renders a signed bridge when future wealth is negative", async ({ page }) => {
  await page.route("**/api/v1/valuation/residual-income?*", async (route) => {
    const upstream = await route.fetch();
    const payload = await upstream.json();
    payload.computed_fair_value = 14.40;
    payload.margin_of_safety_percentage = -95.7;
    payload.valuation_status = "CALCULATED";
    payload.underlying_assumptions = {
      ...payload.underlying_assumptions,
      roe: 0.044,
      cost_of_equity: 0.125,
      book_value_per_share: 21.99,
      pv_future_wealth_per_share: -7.59,
      book_value_component_percentage: null,
      future_wealth_component_percentage: null,
      composition_available: false,
      computed_fair_value: 14.40,
    };
    await route.fulfill({
      response: upstream,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });

  await openValuation(page);

  await expect(page.getByTestId("ri-signed-value-bridge")).toBeVisible();
  await expect(page.getByText("$21.99 − $7.59 = $14.40", { exact: true })).toBeVisible();
  await expect(page.getByText(/ROE \(4\.4%\) is below Cost of Equity \(12\.5%\)/)).toBeVisible();
  await expect(page.getByText("Composition unavailable", { exact: true })).toHaveCount(0);
  const comparisonRow = page.getByText("Residual Income", { exact: true }).first().locator("..").locator("..");
  await expect(comparisonRow.getByText("Available", { exact: true })).toBeVisible();
  await expect(comparisonRow.getByText("$14.40", { exact: true })).toBeVisible();
});

test("DCF deep-dive changes projections while keeping a base-case sensitivity matrix", async ({ page }) => {
  await labelValuationCase("VAL-E2E-DEEP-DIVE-P0-001", "Scenario projections");
  await openValuation(page);
  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).click();

  for (const heading of ["Financial Bridge", "WACC Architecture", "Fundamental Trajectory", "WACC Sensitivity Matrix"]) {
    await expect(page.getByRole("heading", { name: new RegExp(`^${heading}`) }).first()).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: /^\d+-Year Projection Array/ }).first()).toBeVisible();

  const revenueRow = page.getByRole("row").filter({ hasText: "Projected Revenue" });
  const firstProjection = revenueRow.locator("td").nth(1);
  const sensitivityBaseCell = page.getByTestId("sensitivity-base-cell");
  const baseSensitivityValue = await sensitivityBaseCell.innerText();
  await expect(page.getByText("Base-case sensitivity · center matches the Overview DCF")).toBeVisible();
  await page.getByRole("radio", { name: "Bear Case" }).click();
  await expect(sensitivityBaseCell).toHaveText(baseSensitivityValue);
  const bearRevenue = await firstProjection.innerText();
  await page.getByRole("radio", { name: "Bull Case" }).click();
  await expect(sensitivityBaseCell).toHaveText(baseSensitivityValue);
  await expect(firstProjection).not.toHaveText(bearRevenue);
  await page.getByRole("radio", { name: "Base Case" }).click();
  await expect(sensitivityBaseCell).toHaveText(baseSensitivityValue);
  await expectCleanFinancialText(page);
});

test("valuation tabs follow the ARIA keyboard interaction pattern", async ({ page }) => {
  await openValuation(page);

  const overview = page.getByRole("tab", { name: "Valuation Overview" });
  const deepDive = page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" });
  const simulation = page.getByRole("tab", { name: "Simulation & Market Expectations" });

  await overview.focus();
  await overview.press("ArrowRight");
  await expect(deepDive).toBeFocused();
  await expect(deepDive).toHaveAttribute("aria-selected", "true");

  await deepDive.press("End");
  await expect(simulation).toBeFocused();
  await expect(simulation).toHaveAttribute("aria-selected", "true");

  await simulation.press("Home");
  await expect(overview).toBeFocused();
  await expect(overview).toHaveAttribute("aria-selected", "true");

  await page.keyboard.press("Control+3");
  await expect(simulation).toBeFocused();
  await expect(simulation).toHaveAttribute("aria-selected", "true");
});

test("overview compares independent engines and exposes accessible help", async ({ page }) => {
  await openValuation(page);

  await expect(page.getByRole("heading", { name: "Compare valuation methods" })).toBeVisible();
  for (const method of ["Asset-Based", "Discounted Cash Flow", "Dividend Discount Model", "Relative Valuation", "Residual Income"]) {
    await expect(page.getByText(method, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText("no consensus value is inferred", { exact: false })).toBeVisible();

  const help = page
    .getByRole("heading", { name: /^Dividend Discount Model \(DDM\)/ })
    .getByRole("button", { name: "More information" });
  // WebKit does not auto-scroll a programmatically focused element into
  // view the way Chromium/Firefox do, so the geometry assertions below can
  // see the tooltip positioned against an off-screen trigger. Scroll
  // explicitly first so the check reflects tooltip positioning, not browser
  // focus-scroll behavior.
  await help.scrollIntoViewIfNeeded();
  await help.focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeVisible();
  const tooltipGeometry = await tooltip.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      top: rect.top,
      left: rect.left,
      right: rect.right,
      bottom: rect.bottom,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      isPortaledToBody: element.parentElement === document.body,
      hasClippingAncestor: Boolean(element.parentElement?.closest("[class*='overflow-hidden']")),
    };
  });
  expect(tooltipGeometry.top).toBeGreaterThanOrEqual(0);
  expect(tooltipGeometry.left).toBeGreaterThanOrEqual(0);
  expect(tooltipGeometry.right).toBeLessThanOrEqual(tooltipGeometry.viewportWidth);
  expect(tooltipGeometry.bottom).toBeLessThanOrEqual(tooltipGeometry.viewportHeight);
  expect(tooltipGeometry.isPortaledToBody).toBe(true);
  expect(tooltipGeometry.hasClippingAncestor).toBe(false);
  await help.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});

test("DCF uses the sourced API price when the live quote stream is unavailable", async ({ page }) => {
  await page.route("**/api/stocks/TSLA/quote", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Live quote temporarily unavailable" }),
  }));

  await openValuation(page);
  await expect(page.getByText("vs $250.00 market reference", { exact: true })).toBeVisible();
  await expect(page.getByText(/\$0\.00 live/i)).toHaveCount(0);
});

test("DCF surfaces material last-consensus-year dependency", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?ticker=TSLA", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.computed_fair_value = 722.77;
    payload.underlying_assumptions.computed_fair_value = 722.77;
    payload.forward_dcf.fair_value = 700;
    payload.engine_metadata.consensus_horizon_sensitivity = {
      method: "remove_last_consensus_year",
      warning_code: "LAST_CONSENSUS_YEAR_MATERIAL_DEPENDENCY",
      warning_threshold_percentage: 20,
      assessment: "MATERIAL_DEPENDENCY",
      diagnostic_only: true,
      primary_value_basis: "full_valid_consensus",
      full_consensus_years: [2027, 2028, 2029, 2030, 2031],
      removed_consensus_year: 2031,
      last_consensus_revenue_growth_percentage: 32.65,
      last_consensus_revenue_analyst_count: 16,
      full_fair_value: 722.77,
      truncated_fair_value: 423.71,
      absolute_delta: 299.06,
      relative_delta_percentage: 41.38,
      warning_triggered: true,
    };
    await route.fulfill({ response, json: payload });
  });

  await openValuation(page);
  const warning = page.getByTestId("dcf-consensus-horizon-warning");
  await expect(warning.getByText("Consensus-sensitive result")).toBeVisible();
  await expect(warning).toContainText("2031 consensus year");
  await expect(warning).toContainText("$722.77");
  await expect(warning).toContainText("$423.71");
  await expect(warning).toContainText("by 41.4%");
  await expect(warning).toContainText("32.6% revenue growth");
  await expect(warning).toContainText("16 revenue analysts");
  await expect(page.getByText("Full-consensus fair value", { exact: true })).toBeVisible();
  await expect(page.getByTestId("dcf-fair-value")).toHaveText("$722.77");
  await expect(page.getByText("Available · High sensitivity", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await expect(page.getByText("The without-last-year value is diagnostic only.", { exact: false })).toBeVisible();

  await page.getByRole("tab", { name: "Valuation Overview" }).click();
  await page.setViewportSize({ width: 320, height: 800 });
  await expect(warning).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("simulation shows Monte Carlo percentiles and responsive reverse DCF", async ({ page }) => {
  await labelValuationCase("VAL-E2E-SIMULATION-P0-001", "Monte Carlo and reverse DCF controls");
  await openValuation(page);
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();

  await expect(page.getByText("Probabilistic Valuation Range (Monte Carlo)")).toBeVisible();
  await expect(page.getByText("10,000 valid outcomes from 10,000 runs", { exact: false })).toBeVisible();
  for (const percentile of ["10th percentile", "Median", "90th percentile"]) {
    await expect(page.getByText(percentile)).toBeVisible();
  }
  
  // Verify logical constraint of percentiles (P0-08): P10 < P50 < P90
  const p10Value = await page.getByText("10th percentile").locator("..").locator("p").first().innerText();
  const p50Value = await page.getByText("Median").locator("..").locator("p").first().innerText();
  const p90Value = await page.getByText("90th percentile").locator("..").locator("p").first().innerText();
  
  const parseCurrency = (val: string) => parseFloat(val.replace(/[$,]/g, ''));
  expect(parseCurrency(p10Value)).toBeLessThan(parseCurrency(p50Value));
  expect(parseCurrency(p50Value)).toBeLessThan(parseCurrency(p90Value));

  const cagr = page.getByText("Required Stage-1 Revenue Growth").locator("..").locator("span").first();
  const margin = page.getByText(/Required Target EBIT Margin/i).locator("..").locator("span").first();
  
  // Explicitly verify the fixture values for TSLA reverse DCF solver
  await expect(cagr).toHaveText(/12\.0/);
  await expect(margin).toHaveText(/19\.0/);
  await expect(page.getByText(/Stage-1 requirements are not terminal assumptions/)).toBeVisible();

  const scenarioSlider = page.getByRole("slider", { name: "Explore feasible growth and margin pairs" });
  const sliderBox = await scenarioSlider.boundingBox();
  expect(sliderBox).not.toBeNull();
  await scenarioSlider.click({ position: { x: sliderBox!.width - 12, y: sliderBox!.height / 2 } });
  await expect(scenarioSlider).toHaveValue("1");
  await expect(cagr).toHaveText(/9\.6/);
  await scenarioSlider.press("Home");
  await expect(scenarioSlider).toHaveValue("0");
  await scenarioSlider.press("ArrowRight");
  await expect(scenarioSlider).toHaveValue("1");
  await scenarioSlider.press("Home");

  const initialCagr = await cagr.innerText();
  await page.getByLabel("Target price to solve").fill("0");
  await expect(page.getByText("Enter a target price greater than $0.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Solve target" })).toBeDisabled();
  await page.getByLabel("Target price to solve").fill("275");
  await expect(page.getByText(/Results below still reflect \$250\.00/)).toBeVisible();
  await page.getByRole("button", { name: "Solve target" }).click();
  await expect(cagr).not.toHaveText(initialCagr);
  await expect(page.getByText(/Results below reflect the solved \$275\.00 target/)).toBeVisible();
  await page.getByRole("button", { name: "Reset to live" }).click();
  await expect(cagr).toHaveText(/12\.0/);
  await expectCleanFinancialText(page);
});

test("simulation explicitly reports a live price outside the histogram range", async ({ page }) => {
  await page.route("**/api/stocks/TSLA/quote", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ticker: "TSLA",
      status: "success",
      as_of: "2026-07-18T20:00:00Z",
      data: { symbol: "TSLA", price: 600, previous_close: 598, change: 2, change_percent: 0.33, currency: "USD", exchange: "NASDAQ", market_state: "CLOSED" },
      sources: [],
      warnings: [],
    }),
  }));

  await openValuation(page);
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await expect(page.getByRole("status").filter({ hasText: "outside the displayed simulation range" })).toBeVisible();
  await expect(page.getByText(/simulated upper bound/i)).toBeVisible();
});

test("reverse DCF rejects a solver response for the wrong target", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?*implied_target_price=275*", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.implied_expectations.target_price = 250;
    await route.fulfill({ response, json: payload });
  });

  await openValuation(page);
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  const cagr = page.getByText("Required Stage-1 Revenue Growth").locator("..").locator("span").first();
  const initialCagr = await cagr.innerText();
  await page.getByLabel("Target price to solve").fill("275");
  await page.getByRole("button", { name: "Solve target" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "did not match the requested target" })).toBeVisible();
  await expect(cagr).toHaveText(initialCagr);
  await expect(page.getByText(/Results below still reflect \$250\.00/)).toBeVisible();
});

test("partial probabilistic data and missing sensitivity rows remain actionable", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?ticker=TSLA", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.monte_carlo_results.histogram_bins = [];
    payload.forward_dcf.sensitivity_matrix = [];
    await route.fulfill({ response, json: payload });
  });

  await openValuation(page);
  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).click();
  await expect(page.getByText("Sensitivity matrix unavailable")).toBeVisible();
  await expect(page.getByText(/No values were inferred/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry valuation" })).toBeVisible();

  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  for (const percentile of ["10th percentile", "Median", "90th percentile"]) {
    await expect(page.getByText(percentile)).toBeVisible();
  }
  await expect(page.getByText(/histogram bins were not returned/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry histogram" })).toBeVisible();
});

test("missing sourced inputs render an explicit unavailable state", async ({ page }) => {
  await openValuation(page, "NODATA");
  
  // Verify specific missing data warning
  const missingInputsWarning = page.getByText(/Required sourced inputs are missing: current_price, shares_outstanding, cash_flow_from_operations/).first();
  await expect(page.getByText("Inputs unavailable").first()).toBeVisible();
  await expect(missingInputsWarning).toBeVisible();


  // Verify that Monte Carlo handles missing data
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await expect(page.getByText(/Required sourced inputs are missing/).first()).toBeVisible();
  await expectCleanFinancialText(page);
});

test.describe("mobile view", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  
  test("valuation workspace remains usable at a 390px viewport", async ({ page }) => {
    await openValuation(page);
    const mobileNav = page.getByRole("navigation", { name: "Stock workspace views" });
    await expect(mobileNav).toBeVisible();
    for (const label of ["Summary", "News", "Valuation"]) {
      await expect(mobileNav.getByRole("link", { name: label })).toBeVisible();
    }
    const geometry = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth);

    const overviewTab = page.getByRole("tab", { name: "Valuation Overview" });
    const dcfTab = page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" });
    const simulationTab = page.getByRole("tab", { name: "Simulation & Market Expectations" });
    const tangibleToggle = page.getByRole("button", { name: "Tangible Net-Net" });
    for (const tab of [overviewTab, dcfTab, simulationTab]) {
      const box = await tab.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
      expect(box?.x ?? -1).toBeGreaterThanOrEqual(0);
      expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
    }
    expect((await tangibleToggle.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);

    const assumptions = page.getByRole("button", { name: /DCF assumptions/i });
    await expect(assumptions).toHaveAttribute("aria-expanded", "false");
    await assumptions.click();
    await expect(page.getByLabel("Stage 1 growth", { exact: true })).toBeVisible();

    await dcfTab.click();
    const projectionRegion = page.getByRole("region", { name: "Projection years table" });
    await expect(projectionRegion).toBeVisible();
    await expect(page.getByText("Swipe horizontally to compare projection years.")).toBeVisible();
    const projectionGeometry = await projectionRegion.evaluate((node) => ({ scrollWidth: node.scrollWidth, clientWidth: node.clientWidth }));
    expect(projectionGeometry.scrollWidth).toBeGreaterThan(projectionGeometry.clientWidth);

    await simulationTab.click();
    for (const control of [
      page.getByLabel("Target price to solve"),
      page.getByRole("button", { name: "Solve target" }),
      page.getByRole("button", { name: "Reset to live" }),
    ]) {
      const box = await control.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
      expect(box?.width ?? 0).toBeGreaterThan(100);
    }
  });
});

test("race conditions during navigation preserve correct ticker context", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });

  let tslaResolve: () => void;
  const tslaPromise = new Promise<void>((r) => { tslaResolve = r; });

  await page.route("**/api/v1/valuation/dcf?ticker=TSLA", async (route) => {
    await tslaPromise;
    await route.continue();
  });

  await page.route("**/api/search?*", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ symbol: query?.toUpperCase() }),
    });
  });

  // Start at JPM
  await page.goto("/stocks/JPM/valuation");
  await expect(page.getByPlaceholder("Search ticker or company… (JPM)")).toBeVisible();

  // Search for TSLA
  const topbarSearch = page.getByPlaceholder(/Search ticker or company/i);
  await topbarSearch.fill("TSLA");
  await topbarSearch.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/TSLA\/summary$/);
  await expect(page.getByPlaceholder("Search ticker or company… (TSLA)")).toBeVisible();
  
  // Navigate to Valuation Dashboard to trigger the pending DCF fetch
  await page.getByRole("link", { name: "Valuation", exact: true }).click();
  await expect(page).toHaveURL(/\/stocks\/TSLA\/valuation$/);

  // Search for JPM again before TSLA DCF finishes
  await topbarSearch.fill("JPM");
  await topbarSearch.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/JPM\/summary$/);
  await page.locator('a[href$="/valuation"]').first().click();

  // Resolve TSLA now
  tslaResolve!();

  // Verify JPM is the active context
  await expect(page.getByRole("heading", { level: 1, name: "JPM valuation dashboard" })).toBeVisible();
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("Tesla");
});

test("DCF assumption interactions propagate to deep-dive calculations", async ({ page }) => {
  await labelValuationCase("VAL-E2E-ASSUMPTIONS-P0-004", "Assumption validation and propagation");
  await openValuation(page, "TSLA");
  
  const dcfFairValue = page.getByTestId("dcf-fair-value");
  const initialFairValue = await dcfFairValue.innerText();

  await page.getByRole("button", { name: /DCF assumptions/i }).click();
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("");
  await expect(page.getByText("Stage 1 growth is required.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply to workspace" })).toBeDisabled();
  await page.getByRole("button", { name: "Reset all" }).click();
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("10");
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("-1");
  await expect(page.getByText("Stage 1 growth must be at least 0%.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply to workspace" })).toBeDisabled();
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("12.5");
  await page.getByLabel("Discount rate (WACC)", { exact: true }).fill("4");
  await expect(page.getByText("Discount rate (WACC) must be between 5% and 15%.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply to workspace" })).toBeDisabled();
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("12.5");
  await page.getByLabel("Discount rate (WACC)", { exact: true }).fill("8.5");
  await expect(dcfFairValue).toHaveText(initialFairValue);
  await page.getByRole("button", { name: "Apply to workspace" }).click();

  await expect(dcfFairValue).not.toHaveText(initialFairValue);
  const newFairValue = await dcfFairValue.innerText();
  await expect(page.getByRole("status").filter({ hasText: "Saved on this device" })).toBeVisible();

  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).click();
  await expect(page.getByText(newFairValue).first()).toBeVisible();

  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await expect(page.getByText("10,000 valid outcomes from 10,000 runs")).toBeVisible();
  await expect(page.getByText("10th percentile")).toBeVisible();

  await page.getByRole("button", { name: "Reset all" }).click();
  await page.getByRole("tab", { name: "Valuation Overview" }).click();
  await expect(page.getByTestId("dcf-fair-value")).toHaveText(initialFairValue);
  await expectCleanFinancialText(page);
});

test("rounded provider defaults are already active and do not create a false draft", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?ticker=TSLA", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.underlying_assumptions.stage_1_growth_rate = 0.15541943286267124;
    payload.underlying_assumptions.perpetual_growth_rate = 0.020000000000000004;
    payload.underlying_assumptions.discount_rate = 0.10980079233333332;
    await route.fulfill({ response, json: payload });
  });

  await openValuation(page, "TSLA");
  await page.getByRole("button", { name: /DCF assumptions/i }).click();
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("15.54");
  await expect(page.getByText("Model defaults", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply to workspace" })).toBeDisabled();
});

test("failed DCF apply settles and keeps the last complete model retryable", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?*", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    if (params.get("stage_1_growth_rate") === "0.125") {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "temporary" }) });
      return;
    }
    await route.continue();
  });

  await openValuation(page, "TSLA");
  const fairValue = page.getByTestId("dcf-fair-value");
  const initialFairValue = await fairValue.innerText();
  await page.getByRole("button", { name: /DCF assumptions/i }).click();
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("12.5");
  await page.getByRole("button", { name: "Apply to workspace" }).click();
  await expect(page.getByText("Last complete result retained", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry model" })).toBeEnabled();
  await expect(fairValue).toHaveText(initialFairValue);
  await expect(page.getByText("Updating model", { exact: true })).toHaveCount(0);
});

test("whole-company reverse DCF takes precedence over an unavailable SOTP fallback", async ({ page }) => {
  await page.route("**/api/v1/valuation/dcf?*implied_target_price=400*", async (route) => {
    const response = await route.fetch();
    const payload = await response.json();
    payload.reverse_dcf_sotp = {
      is_active: true,
      solver_available: false,
      requested_target_price: 400,
      model_fair_value: 18,
      target_price: 18,
      implied_growth_rate: null,
      segments: [{ name: "Core Business", is_high_growth: false, margin: 10, value: 18, ev_contribution: 18 }],
    };
    await route.fulfill({ response, json: payload });
  });

  await openValuation(page, "TSLA");
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await page.getByLabel("Target price to solve").fill("400");
  await page.getByRole("button", { name: "Solve target" }).click();
  await expect(page.getByText(/Results below reflect the solved \$400\.00 target/)).toBeVisible();
  await expect(page.getByText("Required Stage-1 Revenue Growth").locator("..").locator("span").first()).toHaveText(/19\.2/);
});

test("landing visual stability under reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto("/");
  
  await expect(page.getByRole("heading", { name: /The market has a price/i })).toBeVisible();
  const searchInput = page.getByLabel("Ticker or company name");
  await expect(searchInput).toBeVisible();
  await expect(page.getByRole("button", { name: "Open analysis" })).toBeVisible();
  
  await page.route("**/api/search?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ symbol: "AAPL" }),
    });
  });
  
  await searchInput.fill("AAPL");
  await page.getByRole("button", { name: "Open analysis" }).click();
  
  await expect(page).toHaveURL(/\/stocks\/AAPL\/valuation$/);
});

test("valuation tab content remains visible under reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openValuation(page);
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).click();
  await expect(page.getByText("Probabilistic Valuation Range (Monte Carlo)")).toBeVisible();
});
