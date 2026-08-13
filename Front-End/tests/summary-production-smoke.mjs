import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE_URL = process.env.SUMMARY_SMOKE_BASE_URL || "http://127.0.0.1:3200";
const TICKERS = (process.env.SUMMARY_SMOKE_TICKERS || "AAPL,TSLA,AMZN")
  .split(",")
  .map((ticker) => ticker.trim().toUpperCase())
  .filter(Boolean);

const REQUIRED_SECTIONS = [
  "Price History",
  "Key Facts",
  "Valuation & quality metrics",
  "Business Economics",
  "Revenue Mix Matrix",
  "Supply Chain Exposure & Vulnerabilities",
  "Customer Mix & End Markets",
  "Market & Fundamentals Performance",
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

async function assertWorkspaceNavigation(page) {
  await page.getByRole("link", { name: "Summary" }).first().waitFor({ state: "visible", timeout: 30_000 });
  await page.getByRole("link", { name: "News" }).first().waitFor({ state: "visible", timeout: 30_000 });
  await page.getByRole("link", { name: "Valuation", exact: true }).first().waitFor({ state: "visible", timeout: 30_000 });

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

async function assertSummarySurface(page, ticker) {
  const consoleMessages = [];
  const requestFailures = [];
  page.on("console", (message) => {
    if (!isExpectedConsoleNoise(message)) {
      consoleMessages.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const errorText = request.failure()?.errorText || "";
    const isCancelledRoutePrefetch = errorText.includes("ERR_ABORTED") && request.url().includes("_rsc=");
    if (!isCancelledRoutePrefetch) {
      requestFailures.push(`${request.url()} ${errorText}`);
    }
  });

  await page.goto(`${BASE_URL}/stocks/${ticker}/summary`, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });

  await page.waitForFunction(
    (sections) => sections.every((section) => document.body.innerText.toLowerCase().includes(section.toLowerCase())),
    REQUIRED_SECTIONS,
    { timeout: 60_000 },
  );

  await assertWorkspaceNavigation(page);
  assert.equal(
    await page.getByRole("link", { name: "Summary", exact: true }).first().getAttribute("aria-current"),
    "page",
    "Desktop Summary navigation must expose aria-current",
  );
  await page.waitForTimeout(5_000);
  const observedChartStates = await page.locator("[data-testid$='-chart']").evaluateAll((containers) =>
    containers.map((container) => ({
      target: container.getAttribute("data-testid"),
      state: container.querySelector("[data-chart-state]")?.getAttribute("data-chart-state") || "missing",
      svgCount: container.querySelectorAll("svg").length,
    })),
  );
  console.log(`[summary-smoke] ${ticker} chart states: ${JSON.stringify(observedChartStates)}`);
  await page.waitForFunction(
    () => {
      const targets = ["price-history-chart", "eps-trend-chart", "revenue-earnings-chart"];
      return targets.every((target) => {
        const container = document.querySelector(`[data-testid="${target}"]`);
        const state = container?.querySelector("[data-chart-state]")?.getAttribute("data-chart-state");
        return state === "empty" || (state === "ready" && Boolean(container?.querySelector("svg")));
      });
    },
    { timeout: 30_000 },
  );
  const text = await readBody(page);
  assert.match(text, new RegExp(`${ticker}|${ticker.split("").join("\\s*")}`, "i"), `${ticker} page must identify the selected company`);
  assert.match(text, /Source coverage/i, `${ticker} summary must expose source coverage`);
  assert.match(text, /investment snapshot/i, `${ticker} summary must expose the decision-oriented investment snapshot`);
  assert.match(text, /Filing evidence/i, `${ticker} summary must identify the business evidence rail`);
  await page.getByRole("link", { name: new RegExp(`Open ${ticker} fair value`, "i") }).waitFor({ state: "visible" });
  await page.getByText("View price history data", { exact: true }).waitFor({ state: "visible" });
  await page.getByText("View quarterly EPS data", { exact: true }).waitFor({ state: "visible" });
  await page.getByText("View annual performance data", { exact: true }).waitFor({ state: "visible" });
  await page.getByText("Latest reported movement", { exact: true }).waitFor({ state: "visible" });
  assert.ok(
    await page.locator('[data-testid="price-history-chart"] [stroke="#22D3EE"]').count(),
    "Price history must use the neutral Data Cyan series color",
  );
  assert.ok(
    await page.locator('[data-testid="revenue-earnings-chart"] [fill="#EFFAF4"]').count(),
    "Earnings comparison must use Strong Ink instead of a positive/negative semantic color",
  );
  const revenueCategoryEncoding = await page.locator(".summary-revenue-mix-bar").first().evaluate((bar) =>
    Array.from(bar.children).slice(0, 3).map((segment) => ({
      color: getComputedStyle(segment).backgroundColor,
      separator: getComputedStyle(segment).borderRightWidth,
    })),
  );
  const expectedColors = ["rgb(167, 139, 250)", "rgb(239, 250, 244)", "rgb(144, 176, 158)"];
  assert.deepEqual(
    revenueCategoryEncoding.map((segment) => segment.color),
    expectedColors.slice(0, revenueCategoryEncoding.length),
    "Revenue Mix must use the violet-led categorical palette instead of adjacent Sky and Cyan",
  );
  assert.ok(
    revenueCategoryEncoding.length <= 1 || revenueCategoryEncoding.slice(0, -1).every((segment) => segment.separator === "1px"),
    "Adjacent Revenue Mix categories must have dark one-pixel separators",
  );
  const revenueCategoryMarkers = await page.locator(".summary-revenue-mix-bar").first().locator(":scope > div").evaluateAll(
    (segments) => segments.slice(0, 3).map((segment) => segment.textContent?.trim()),
  );
  const expectedMarkers = ["A", "B", "C"];
  assert.deepEqual(
    revenueCategoryMarkers,
    expectedMarkers.slice(0, revenueCategoryMarkers.length),
    "Revenue Mix bars must expose stable non-color category markers",
  );
  const annualChartTicks = await page.locator('[data-testid="revenue-earnings-chart"] .recharts-cartesian-axis-tick-value').allTextContents();
  const annualYAxisTicks = annualChartTicks.filter((tick) => /^\$[\d.]+B$/.test(tick));
  assert.ok(
    annualYAxisTicks.length >= 2,
    `Annual performance y-axis must expose USD billions (${annualChartTicks.join(", ")})`,
  );
  const initialRangeAnimation = await page.locator('[data-testid="price-history-chart"]').evaluate(
    (element) => getComputedStyle(element).animationName,
  );
  assert.equal(initialRangeAnimation, "none", "Price history must not animate on initial load");
  await page.getByRole("button", { name: "1Y", exact: true }).click();
  await page.locator('[data-testid="price-history-chart"] svg').waitFor({ state: "visible" });
  const interactedRangeAnimation = await page.locator('[data-testid="price-history-chart"]').evaluate(
    (element) => getComputedStyle(element).animationName,
  );
  assert.equal(interactedRangeAnimation, "summary-chart-range-in", "Price history range changes must provide restrained state feedback");
  const snapshot = page.locator("#investment-snapshot");
  if (text.includes("Risk evidence incomplete")) {
    assert.equal(
      await snapshot.getByText("Material risk evidence", { exact: true }).count(),
      0,
      "Incomplete AI risk must be demoted from the primary snapshot",
    );
  }
  assert.doesNotMatch(text, /\bNaN\b/i, "Summary UI must not render NaN");
  assert.doesNotMatch(text, /\bInfinity\b/i, "Summary UI must not render Infinity");
  assert.doesNotMatch(text, />null<|\bnull\b/i, "Summary UI must not leak null values");

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNav = page.getByRole("navigation", { name: "Stock workspace views" });
  await mobileNav.waitFor({ state: "visible" });
  const sectionNav = page.getByRole("navigation", { name: "Summary sections" });
  await sectionNav.waitFor({ state: "visible" });
  for (const label of ["Summary", "News", "Valuation"]) {
    const link = mobileNav.getByRole("link", { name: label });
    const box = await link.boundingBox();
    assert.ok(box && box.height >= 44, `${label} mobile navigation target must be at least 44px high`);
  }
  const viewportGeometry = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert.ok(
    viewportGeometry.scrollWidth <= viewportGeometry.clientWidth,
    `Summary must not overflow horizontally at 390px (${viewportGeometry.scrollWidth} > ${viewportGeometry.clientWidth})`,
  );
  const mobileAxisFontSizes = await page.locator(".summary-chart .recharts-cartesian-axis-tick-value").evaluateAll((ticks) =>
    ticks.map((tick) => Number.parseFloat(getComputedStyle(tick).fontSize)),
  );
  assert.ok(
    mobileAxisFontSizes.length && mobileAxisFontSizes.every((size) => size >= 12),
    `Mobile chart ticks must be at least 12px (${mobileAxisFontSizes.join(", ")})`,
  );
  const mobileRevenueBar = await page.locator(".summary-revenue-mix-bar").first().boundingBox();
  assert.ok(mobileRevenueBar && mobileRevenueBar.height >= 16, `Mobile Revenue Mix bar must be at least 16px high (${mobileRevenueBar?.height})`);
  const mobileSwatchSizes = await page.locator(".summary-revenue-swatch").evaluateAll((swatches) =>
    swatches.map((swatch) => {
      const box = swatch.getBoundingClientRect();
      return { width: box.width, height: box.height };
    }),
  );
  assert.ok(
    mobileSwatchSizes.length && mobileSwatchSizes.every((swatch) => swatch.width >= 12 && swatch.height >= 12),
    `Mobile Revenue Mix swatches must be at least 12px (${JSON.stringify(mobileSwatchSizes)})`,
  );
  const trustControlSizes = await page.locator(".summary-trust-control:visible").evaluateAll((controls) =>
    controls.map((control) => {
      const box = control.getBoundingClientRect();
      return { label: control.textContent?.trim() || control.getAttribute("aria-label") || "control", width: box.width, height: box.height };
    }),
  );
  for (const control of trustControlSizes) {
    assert.ok(
      control.width >= 43.9 && control.height >= 43.9,
      `${control.label} trust control must be at least 44x44px (${control.width}x${control.height})`,
    );
  }

  const sourceHeaderGeometry = await page.getByRole("heading", { name: "Market & Fundamentals Performance" }).evaluate((heading) => {
    const header = heading.parentElement?.parentElement;
    const sourceRow = header?.lastElementChild;
    const headingBox = heading.getBoundingClientRect();
    const sourceBox = sourceRow?.getBoundingClientRect();
    const headerBox = header?.getBoundingClientRect();
    return {
      sourceBelowTitle: Boolean(sourceBox && sourceBox.top >= headingBox.bottom),
      sourceUsesHeaderWidth: Boolean(sourceBox && headerBox && sourceBox.width >= headerBox.width * 0.9),
    };
  });
  assert.ok(sourceHeaderGeometry.sourceBelowTitle, "Mobile source attribution must sit below the card title");
  assert.ok(sourceHeaderGeometry.sourceUsesHeaderWidth, "Mobile source attribution must receive a full-width row");

  await page.setViewportSize({ width: 320, height: 844 });
  const narrowViewportGeometry = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert.ok(
    narrowViewportGeometry.scrollWidth <= narrowViewportGeometry.clientWidth,
    `Summary must not overflow horizontally at 320px (${narrowViewportGeometry.scrollWidth} > ${narrowViewportGeometry.clientWidth})`,
  );
  const yAxisLabelBoxes = await page.locator('[data-testid="revenue-earnings-chart"] .recharts-cartesian-axis-tick-value').evaluateAll((labels) => labels
    .filter((label) => /^\$[\d.]+B$/.test(label.textContent?.trim() || ""))
    .map((label) => {
      const box = label.getBoundingClientRect();
      return { left: box.left, right: box.right };
    }));
  assert.ok(
    yAxisLabelBoxes.length && yAxisLabelBoxes.every((box) => box.left >= 0 && box.right <= 320),
    `Annual chart Y-axis labels must remain inside a 320px viewport (${JSON.stringify(yAxisLabelBoxes)})`,
  );

  await page.evaluate(() => window.scrollTo(0, 2200));
  await page.waitForTimeout(250);
  const mobileNavBox = await mobileNav.boundingBox();
  const appBarBox = await page.locator(".workspace-topbar").boundingBox();
  const sectionNavState = await sectionNav.evaluate((navigation) => ({
    position: getComputedStyle(navigation).position,
    top: navigation.getBoundingClientRect().top,
  }));
  assert.ok(appBarBox && Math.abs(appBarBox.y) <= 1, `Mobile app bar must remain sticky (y=${appBarBox?.y})`);
  assert.ok(
    mobileNavBox && appBarBox && mobileNavBox.y >= appBarBox.y && mobileNavBox.y + mobileNavBox.height <= appBarBox.y + appBarBox.height + 1,
    `Mobile route navigation must remain inside the sticky app bar (${JSON.stringify({ mobileNavBox, appBarBox })})`,
  );
  assert.notEqual(sectionNavState.position, "sticky", "Summary section navigation must not remain sticky on mobile");
  assert.ok(sectionNavState.top < 0, `Summary section navigation must scroll away with content (y=${sectionNavState.top})`);

  assert.deepEqual(requestFailures, [], `${ticker} page must not have failed browser requests`);
  assert.deepEqual(consoleMessages, [], `${ticker} page must not log runtime errors`);
}

const failures = [];
const browser = await chromium.launch({ headless: true });
try {
  for (const ticker of TICKERS) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
    try {
      await assertSummarySurface(page, ticker);
      console.log(`[summary-smoke] ${ticker} passed`);
    } catch (error) {
      failures.push(`${ticker}: ${error.message}`);
    } finally {
      await page.close().catch(() => {});
    }
  }
} finally {
  await browser.close().catch(() => {});
}

if (failures.length) {
  throw new Error(`Summary production smoke failed:\n${failures.join("\n")}`);
}
