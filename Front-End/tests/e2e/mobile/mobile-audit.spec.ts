import { expect, test, type Page } from "@playwright/test";
import { confirmSignup } from "../auth-helpers";

import {
  expectMobileIntegrity,
  expectPrimaryTouchTargets,
  expectWcag22AA,
} from "./mobile-assertions";

const SAVED_STOCKS_STORAGE_KEY = "valuator:saved-stocks:v1";

const routeCases = [
  { name: "landing", path: "/", ready: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { name: "login", path: "/login", ready: (page: Page) => page.getByRole("heading", { name: "Sign in" }) },
  { name: "register", path: "/register", ready: (page: Page) => page.getByRole("heading", { name: "Create your account" }) },
  { name: "forgot password", path: "/forgot-password", ready: (page: Page) => page.getByRole("heading", { name: "Reset password" }) },
  { name: "account", path: "/account", ready: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { name: "summary", path: "/stocks/TSLA/summary", ready: (page: Page) => page.getByRole("heading", { level: 1 }) },
  { name: "news", path: "/stocks/TSLA/news", ready: (page: Page) => page.getByRole("heading", { name: "TSLA news intelligence" }) },
  { name: "valuation", path: "/stocks/TSLA/valuation", ready: (page: Page) => page.getByRole("tab", { name: "Valuation Overview" }) },
] as const;

async function openReadyPage(page: Page, path: string, ready: (page: Page) => ReturnType<Page["locator"]>) {
  await page.goto(path);
  await expect(ready(page).first()).toBeVisible();
}

for (const routeCase of routeCases) {
  test(`${routeCase.name} reflows and exposes an accessible mobile surface`, async ({ page }) => {
    await openReadyPage(page, routeCase.path, routeCase.ready);
    await expectMobileIntegrity(page);
    await expectWcag22AA(page);
    await expectPrimaryTouchTargets(page);
  });
}

test("landing search and all stock workspace routes remain reachable by touch", async ({ page }) => {
  await page.route("**/api/stocks/TSLA/news", async (route) => {
    expect(new URL(route.request().url()).origin).toBe(new URL(page.url()).origin);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ticker: "TSLA",
        status: "success",
        articles: [
          {
            id: 1,
            headline: "Tesla beats earnings estimates",
            summary: "Record deliveries in Q3.",
            source: "Financial Times",
            timestamp: Math.floor(Date.now() / 1000) - 3600,
            url: "https://example.com/1",
            topic: "Earnings",
          },
          {
            id: 2,
            headline: "Tesla announces new factory",
            summary: "Expansion continues in Europe.",
            source: "Bloomberg",
            timestamp: Math.floor(Date.now() / 1000) - 86400,
            url: "https://example.com/2",
            topic: "Expansion",
          },
        ],
      }),
    });
  });

  await page.goto("/");
  await page.getByLabel("Ticker or company name").fill("TSLA");
  await page.getByRole("button", { name: "Open analysis" }).tap();
  await expect(page).toHaveURL(/\/stocks\/TSLA\/valuation$/);

  const navigation = page.getByRole("navigation", { name: "Stock workspace views" });
  for (const label of ["Summary", "News", "Valuation"]) {
    const link = navigation.getByRole("link", { name: label });
    await expect(link).toBeVisible();
    const box = await link.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }

  await navigation.getByRole("link", { name: "Summary" }).tap();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectMobileIntegrity(page);

  await navigation.getByRole("link", { name: "News" }).tap();
  await expect(page.getByRole("heading", { name: "TSLA news intelligence" })).toBeVisible();
  await page.getByPlaceholder("Search headlines, summaries, or sources").fill("earnings");
  await expect(page.getByRole("heading", { name: "Tesla beats earnings estimates" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tesla announces new factory" })).not.toBeVisible();
  await expectMobileIntegrity(page);
  await expectWcag22AA(page);
  await expectPrimaryTouchTargets(page);

  await navigation.getByRole("link", { name: "Valuation" }).tap();
  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).tap();
  await expect(page.getByRole("region", { name: "Projection years table" })).toBeVisible();
  await expectMobileIntegrity(page);
  await expectPrimaryTouchTargets(page);
});

test("guest auth and valuation price marker remain legible on a compact landing page", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.route("**/api/featured-walkthrough", async (route) => {
    const engine = (computedFairValue: number) => ({
      computed_fair_value: computedFairValue,
      valuation_status: "CALCULATED",
      valuation_methodology: "Deterministic mobile fixture",
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ticker: "MSFT",
        company_name: "Microsoft Corporation",
        fetched_at: "2026-08-12T04:28:00Z",
        cache_ttl_seconds: 3600,
        status: "complete",
        providers: ["Recorded provider snapshot"],
        warnings: [],
        engines: {
          asset: engine(80),
          dcf: {
            ...engine(400),
            current_price: 559.35,
            monte_carlo_results: { bear_p10: 340, base_p50: 400, bull_p90: 470 },
            implied_expectations: {},
            underlying_assumptions: {
              telemetry: { current_price: 559.35, risk_free_rate: 0.047, cost_of_equity: 0.111 },
              computational_warnings: ["No feasible implied-expectations solution."],
            },
          },
          ddm: engine(95),
          relative: engine(520),
          residual: engine(110),
        },
      }),
    });
  });
  await page.goto("/");

  await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign up", exact: true })).toBeVisible();

  const expectationsStage = page.locator('[data-instrument-stage="expectations"]');
  const priceLabel = expectationsStage.getByTestId("valuation-plot-price-label");
  const maxLabel = expectationsStage.getByTestId("valuation-plot-max-label");
  await expect(priceLabel).toBeVisible();
  await expect(maxLabel).toBeVisible();
  const priceBox = await priceLabel.boundingBox();
  const maxBox = await maxLabel.boundingBox();
  expect(priceBox).not.toBeNull();
  expect(maxBox).not.toBeNull();
  const overlaps = !(
    priceBox!.x + priceBox!.width <= maxBox!.x
    || maxBox!.x + maxBox!.width <= priceBox!.x
    || priceBox!.y + priceBox!.height <= maxBox!.y
    || maxBox!.y + maxBox!.height <= priceBox!.y
  );
  expect(overlaps).toBe(false);
  await expectMobileIntegrity(page);
  await expectPrimaryTouchTargets(page);
});

test("valuation telemetry, sticky tables and WACC equation retain mobile hierarchy", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openReadyPage(page, "/stocks/TSLA/valuation", routeCases[7].ready);

  const telemetryCells = page.getByTestId("valuation-telemetry-grid").locator(":scope > *");
  await expect(telemetryCells).toHaveCount(4);
  const telemetryBoxes = await telemetryCells.evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, right: rect.right };
  }));
  expect(telemetryBoxes[0].y).toBeCloseTo(telemetryBoxes[1].y, 0);
  expect(telemetryBoxes[2].y).toBeCloseTo(telemetryBoxes[3].y, 0);
  expect(telemetryBoxes[2].y).toBeGreaterThan(telemetryBoxes[0].y);
  expect(Math.max(...telemetryBoxes.map((box) => box.right))).toBeLessThanOrEqual(360);

  await page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" }).tap();
  const equity = page.getByTestId("wacc-equity-term");
  const plus = page.getByLabel("plus");
  const debt = page.getByTestId("wacc-debt-term");
  const equals = page.getByLabel("equals");
  const result = page.getByTestId("wacc-result");
  for (const item of [equity, plus, debt, equals, result]) await expect(item).toBeVisible();
  const [equityBox, plusBox, debtBox, equalsBox, resultBox] = await Promise.all(
    [equity, plus, debt, equals, result].map((locator) => locator.boundingBox()),
  );
  expect(equityBox!.y + equityBox!.height).toBeLessThanOrEqual(plusBox!.y);
  expect(plusBox!.y + plusBox!.height).toBeLessThanOrEqual(debtBox!.y);
  expect(debtBox!.y + debtBox!.height).toBeLessThanOrEqual(equalsBox!.y);
  expect(equalsBox!.y + equalsBox!.height).toBeLessThanOrEqual(resultBox!.y);

  for (const table of [
    { region: page.getByRole("region", { name: "Projection years table" }), sticky: page.getByTestId("projection-sticky-label") },
    { region: page.getByRole("region", { name: "Sensitivity matrix" }), sticky: page.getByTestId("sensitivity-sticky-label") },
  ]) {
    await expect(table.region).toBeVisible();
    await table.region.evaluate((node) => node.scrollIntoView({ block: "center" }));
    await table.region.evaluate((node) => { node.scrollLeft = node.scrollWidth; });
    const overlay = await table.sticky.evaluate((node) => {
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      const topElement = document.elementFromPoint(rect.right - 4, rect.y + rect.height / 2);
      return {
        position: style.position,
        backgroundColor: style.backgroundColor,
        zIndex: Number(style.zIndex),
        ownsPoint: Boolean(topElement?.closest('[data-testid="projection-sticky-label"], [data-testid="sensitivity-sticky-label"]')),
      };
    });
    expect(overlay.position).toBe("sticky");
    expect(overlay.backgroundColor).toBe("rgb(9, 10, 11)");
    expect(overlay.zIndex).toBeGreaterThan(0);
    expect(overlay.ownsPoint).toBe(true);
  }

  await expectMobileIntegrity(page);
});

test("a long saved-stocks account remains searchable and pageable by touch", async ({ page }) => {
  const base = Date.now();
  const tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "MA", "AVGO", "WMT"];
  const items = tickers.map((ticker, index) => ({
    ticker,
    addedAt: new Date(base - index * 1_000).toISOString(),
    lastVisitedAt: new Date(base - index * 1_000).toISOString(),
    lastSection: index % 2 === 0 ? "valuation" : "summary",
  }));

  await page.addInitScript(({ key, savedItems }) => {
    window.localStorage.setItem(key, JSON.stringify({ version: 1, items: savedItems }));
  }, { key: SAVED_STOCKS_STORAGE_KEY, savedItems: items });
  await page.route("**/api/stocks/snapshots?*", async (route) => {
    const requestUrl = new URL(route.request().url());
    const requestedTickers = (requestUrl.searchParams.get("tickers") ?? "").split(",").filter(Boolean);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "success",
        as_of: new Date(base).toISOString(),
        warnings: [],
        data: requestedTickers.map((ticker) => ({
          ticker,
          company_name: ticker === "MSFT" ? "Microsoft Corporation" : `${ticker} Holdings`,
          price: 100 + tickers.indexOf(ticker),
          change: 0,
          change_percent: 0,
          currency: "USD",
          status: "success",
          as_of: new Date(base).toISOString(),
          warnings: [],
          sources: [],
        })),
      }),
    });
  });

  await page.goto("/account");
  const panel = page.getByRole("region", { name: "Saved Stocks" });
  await expect(panel.locator("article")).toHaveCount(10);
  await panel.getByLabel("Search saved stocks").fill("Microsoft");
  await expect(panel.getByText("MSFT", { exact: true })).toBeVisible();
  await panel.getByLabel("Search saved stocks").fill("");
  await panel.getByLabel("Sort saved stocks").selectOption("ticker");
  await panel.getByRole("button", { name: "Next" }).tap();
  await expect(panel.getByText("2 / 2")).toBeVisible();
  await expectMobileIntegrity(page);
  await expectWcag22AA(page);
  await expectPrimaryTouchTargets(page);
});

test("mobile registration validation and password recovery remain usable", async ({ page }, testInfo) => {
  const email = `mobile-${testInfo.project.name}-${Date.now()}@example.com`;
  await page.goto("/register?next=%2Faccount");
  await page.getByLabel("Email").fill("invalid-email");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await page.getByLabel("Confirm Password").fill("different");
  await page.getByRole("button", { name: "Create account" }).tap();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveAttribute("aria-invalid", "true");
  await expectMobileIntegrity(page);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("password123");
  await page.getByLabel("Confirm Password").fill("password123");
  await page.getByRole("button", { name: "Create account" }).tap();
  await expect(page.getByText("Check your inbox")).toBeVisible();
  await confirmSignup(page, email, "/account");
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByText(email)).toBeVisible();
  await expectMobileIntegrity(page);

  await page.getByRole("button", { name: "Log out" }).first().tap();
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill("wrong-address@example.com");
  await page.getByRole("button", { name: "Send reset link" }).tap();
  await expect(page.getByText("Check your inbox")).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send another link" }).tap();
  await expect(page.getByText("Check your inbox")).toBeVisible();
  await expectMobileIntegrity(page);
  await expectPrimaryTouchTargets(page);
});

test("compact and landscape viewports do not hide core routes or actions", async ({ page }) => {
  for (const viewport of [
    { width: 320, height: 800 },
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 844, height: 390 },
  ]) {
    await page.setViewportSize(viewport);
    for (const routeCase of [routeCases[0], routeCases[5], routeCases[6], routeCases[7]]) {
      await openReadyPage(page, routeCase.path, routeCase.ready);
      await expectMobileIntegrity(page);
    }
  }
});

test("mobile unavailable states stay actionable and within the viewport", async ({ page }) => {
  await page.goto("/stocks/MISSING/summary");
  await expect(page.getByText("Price history is unavailable from the current provider.").first()).toBeVisible();
  await expectMobileIntegrity(page);

  await page.goto("/stocks/NODATA/valuation");
  await expect(page.getByText("Inputs unavailable").first()).toBeVisible();
  await page.getByRole("tab", { name: "Simulation & Market Expectations" }).tap();
  await expect(page.getByText(/Required sourced inputs are missing/).first()).toBeVisible();
  await expect(page.locator("#valuation-panel-sim")).toHaveCSS("opacity", "1");
  await expectMobileIntegrity(page);
  await expectWcag22AA(page);
  await expectPrimaryTouchTargets(page);
});
