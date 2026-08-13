import { expect, test } from "@playwright/test";
import { allure } from "allure-playwright";
import { confirmSignup } from "./auth-helpers";

const FIXTURE_CONTROL_URL = process.env.E2E_FIXTURE_CONTROL_URL ?? "http://127.0.0.1:8300";

const STORAGE_KEY = "valuator:saved-stocks:v1";

async function labelSavedCase(id: string, story: string) {
  await allure.epic("Instrument Workspace");
  await allure.feature("Saved Stocks");
  await allure.story(story);
  await allure.layer("frontend-e2e");
  await allure.label("priority", "P0");
  await allure.severity("blocker");
  await allure.owner("Thanadon");
  await allure.testCaseId(id);
}

function emailFor(prefix: string, projectName: string): string {
  return `${prefix}-${projectName.replace(/[^a-z0-9]/gi, "-")}-${Date.now()}@example.com`.toLowerCase();
}

test.describe("Saved Stocks", () => {
  test("guest save persists, returns to the last section, and can be removed", async ({ page }) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-001", "Guest saved stocks");

    await page.goto("/stocks/TSLA/summary");
    await page.getByRole("button", { name: "Save TSLA to saved stocks" }).first().click();
    await expect(page.getByText("TSLA saved on this device")).toBeVisible();
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).not.toBeNull();

    await page.getByRole("button", { name: "Not now" }).click();
    await page.reload();
    await expect(page.getByRole("button", { name: "Remove TSLA from saved stocks" }).first()).toBeVisible();

    await page.goto("/");
    const panel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(panel.getByText("Tesla, Inc.")).toBeVisible();
    await panel.getByRole("link", { name: /TSLA/ }).click();
    await expect(page).toHaveURL(/\/stocks\/TSLA\/summary$/);
    await expect(page.getByRole("navigation", { name: "Stock workspace views" })).toBeVisible();

    await page.goto("/");
    await page.getByRole("region", { name: "Saved Stocks" }).getByRole("button", { name: "Remove TSLA from saved stocks" }).click();
    await expect(page.getByText("TSLA removed from saved stocks.")).toBeVisible();
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(page.getByText("TSLA restored to saved stocks.")).toBeVisible();
    await expect(page.getByRole("region", { name: "Saved Stocks" }).getByText("TSLA", { exact: true })).toBeVisible();

    await page.getByRole("region", { name: "Saved Stocks" }).getByRole("button", { name: "Remove TSLA from saved stocks" }).click();
    await expect(page.getByText("No saved stocks on this device yet.")).toBeVisible();
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();
  });

  test("account sign-up merges guest data, isolates users, and clears private data on logout", async ({ page, browser }, testInfo) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-002", "Account sync and isolation");
    const email = emailFor("saved-owner", testInfo.project.name);
    const password = "password123";

    await page.goto("/stocks/TSLA/valuation");
    await page.getByRole("button", { name: "Save TSLA to saved stocks" }).first().click();
    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email, "/account");

    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText("Synced to your account")).toBeVisible();
    await expect(page.getByRole("region", { name: "Saved Stocks" }).getByText("TSLA", { exact: true })).toBeVisible();
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();

    const otherContext = await browser.newContext();
    const otherPage = await otherContext.newPage();
    const otherEmail = emailFor("saved-other", testInfo.project.name);
    await otherPage.goto("/register?next=%2Faccount");
    await otherPage.getByLabel("Email").fill(otherEmail);
    await otherPage.getByLabel("Password", { exact: true }).fill(password);
    await otherPage.getByLabel("Confirm Password").fill(password);
    await otherPage.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(otherPage, otherEmail, "/account");
    await expect(otherPage).toHaveURL(/\/account$/);
    await expect(otherPage.getByText("No saved stocks in your account yet.")).toBeVisible();
    await otherContext.close();

    await page.getByRole("button", { name: "Log out" }).first().click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText("No saved stocks on this device yet.")).toBeVisible();

    await page.goto("/stocks/JPM/news");
    await page.getByRole("button", { name: "Save JPM to saved stocks" }).first().click();
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).not.toBeNull();

    await page.goto("/login?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/account$/);
    const accountPanel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(accountPanel.getByText("TSLA", { exact: true })).toBeVisible();
    await expect(accountPanel.getByText("JPM", { exact: true })).toBeVisible();
    await expect(accountPanel.locator('[role="alert"]')).toHaveCount(0);
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();

    await page.goto("/stocks/TSLA/valuation");
    await expect(page.getByRole("button", { name: "Remove TSLA from saved stocks" }).first()).toBeVisible();
  });

  test("landing shows three recent stocks while account manages the complete guest list", async ({ page }) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-003", "Saved list pagination boundary");
    const base = Date.now();
    const tickers = ["TSLA", "JPM", "AAPL", "MSFT", "NVDA", "AMD", "META"];
    const items = tickers.map((ticker, index) => ({
      ticker,
      addedAt: new Date(base - index * 1_000).toISOString(),
      lastVisitedAt: new Date(base - index * 1_000).toISOString(),
      lastSection: index % 2 === 0 ? "valuation" : "summary",
    }));

    await page.addInitScript(({ key, savedItems }) => {
      window.localStorage.setItem(key, JSON.stringify({ version: 1, items: savedItems }));
    }, { key: STORAGE_KEY, savedItems: items });
    await page.goto("/");

    const landingPanel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(landingPanel.locator("article")).toHaveCount(3);
    await expect(landingPanel.getByText("3 of 7 shown")).toBeVisible();
    await landingPanel.getByRole("link", { name: "View all saved" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("region", { name: "Saved Stocks" }).locator("article")).toHaveCount(7);
  });

  test("account searches, sorts, batches, and paginates a long list without nested scrolling", async ({ page }) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-007", "Long saved-list management");
    const base = Date.now();
    const tickers = [
      "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "MA",
      "AVGO", "WMT", "LLY", "ORCL", "NFLX", "COST", "AMD", "INTC", "CRM", "IBM", "ADBE",
    ];
    const items = tickers.map((ticker, index) => ({
      ticker,
      addedAt: new Date(base - index * 1_000).toISOString(),
      lastVisitedAt: new Date(base - index * 1_000).toISOString(),
      lastSection: index % 2 === 0 ? "valuation" : "summary",
    }));
    const snapshotBatchSizes: number[] = [];

    await page.addInitScript(({ key, savedItems }) => {
      window.localStorage.setItem(key, JSON.stringify({ version: 1, items: savedItems }));
    }, { key: STORAGE_KEY, savedItems: items });
    await page.route("**/api/stocks/snapshots?*", async (route) => {
      const requestUrl = new URL(route.request().url());
      const requestedTickers = (requestUrl.searchParams.get("tickers") ?? "").split(",").filter(Boolean);
      snapshotBatchSizes.push(requestedTickers.length);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          as_of: new Date(base).toISOString(),
          warnings: [],
          data: requestedTickers.map((ticker) => {
            const index = tickers.indexOf(ticker);
            return {
              ticker,
              company_name: ticker === "MSFT" ? "Microsoft Corporation" : `${ticker} Holdings`,
              price: 100 + index,
              change: index,
              change_percent: index,
              currency: "USD",
              status: "success",
              as_of: new Date(base).toISOString(),
              warnings: [],
              sources: [],
            };
          }),
        }),
      });
    });

    await page.goto("/account");
    const panel = page.getByRole("region", { name: "Saved Stocks" });
    const list = panel.getByTestId("saved-stocks-account-list");
    await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Create account", exact: true })).toBeVisible();
    await expect(panel.locator("article")).toHaveCount(10);
    await expect(panel.getByText("1 / 3")).toBeVisible();
    await expect.poll(() => snapshotBatchSizes.reduce((total, size) => total + size, 0)).toBe(21);
    expect(Math.max(...snapshotBatchSizes)).toBeLessThanOrEqual(20);

    const listMetrics = await list.evaluate((element) => ({
      clientHeight: element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
      scrollHeight: element.scrollHeight,
    }));
    expect(listMetrics.overflowY).toBe("visible");
    expect(listMetrics.scrollHeight).toBeLessThanOrEqual(listMetrics.clientHeight);

    await panel.getByLabel("Search saved stocks").fill("Microsoft");
    await expect(panel.locator("article")).toHaveCount(1);
    await expect(panel.getByText("MSFT", { exact: true })).toBeVisible();
    await expect(panel.getByText("1 of 21 matched")).toBeVisible();

    await panel.getByLabel("Search saved stocks").fill("");
    await panel.getByLabel("Sort saved stocks").selectOption("ticker");
    await expect(panel.locator("article").first().getByText("AAPL", { exact: true })).toBeVisible();

    await panel.getByRole("button", { name: "Next" }).click();
    await panel.getByRole("button", { name: "Next" }).click();
    await expect(panel.getByText("3 / 3")).toBeVisible();
    await expect(panel.locator("article")).toHaveCount(1);
  });

  test("failed restore keeps an actionable retry until the stock is restored", async ({ page, request }, testInfo) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-008", "Saved stock restore recovery");
    const email = emailFor("saved-restore", testInfo.project.name);
    const password = "password123";

    await page.goto("/register?next=%2Fstocks%2FTSLA%2Fsummary");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email, "/stocks/TSLA/summary");
    await expect(page).toHaveURL(/\/stocks\/TSLA\/summary$/);
    await page.getByRole("button", { name: "Save TSLA to saved stocks" }).first().click();
    await page.goto("/account");

    await request.post(`${FIXTURE_CONTROL_URL}/__test__/saved-stocks-fail-next`, {
      data: { email, merges: 1 },
    });
    const panel = page.getByRole("region", { name: "Saved Stocks" });
    await panel.getByRole("button", { name: "Remove TSLA from saved stocks" }).click();
    await panel.getByRole("button", { name: "Undo" }).click();
    await expect(panel.getByText("TSLA could not be restored. Your removal is unchanged.")).toBeVisible();
    await panel.getByRole("button", { name: "Try restore" }).click();
    await expect(panel.getByText("TSLA restored to saved stocks.")).toBeVisible();
    await expect(panel.getByText("TSLA", { exact: true })).toBeVisible();
  });

  test("authenticated landing uses a full-width launcher without nested saved-stock scrolling", async ({ page }, testInfo) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-005", "Landing layout stability");
    await page.setViewportSize({ width: 1920, height: 972 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const email = emailFor("saved-launcher", testInfo.project.name);
    const password = "password123";

    const base = Date.now();
    const items = ["AAPL", "MSFT", "NVDA", "AMD", "META", "JPM"].map((ticker, index) => ({
      ticker,
      addedAt: new Date(base - index * 1_000).toISOString(),
      lastVisitedAt: new Date(base - index * 1_000).toISOString(),
      lastSection: index % 2 === 0 ? "valuation" : "summary",
    }));

    await page.addInitScript(({ key, savedItems }) => {
      window.localStorage.setItem(key, JSON.stringify({ version: 1, items: savedItems }));
    }, { key: STORAGE_KEY, savedItems: items });
    await page.goto("/register?next=%2F");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email);

    await expect(page).toHaveURL(/\/$/);
    const headline = page.getByRole("heading", { name: "Continue your valuation work." });
    const panel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(headline).toBeVisible();
    await expect(panel.locator("article")).toHaveCount(3);
    await expect(panel.getByRole("link", { name: "View all saved" })).toBeVisible();
    await expect(panel.getByRole("button", { name: /Hide|Show/ })).toHaveCount(0);

    const [headlinePosition, panelPosition] = await Promise.all([
      headline.boundingBox(),
      panel.boundingBox(),
    ]);
    expect(headlinePosition).not.toBeNull();
    expect(panelPosition).not.toBeNull();
    expect(Math.abs(panelPosition!.x - headlinePosition!.x)).toBeLessThanOrEqual(2);
    expect(panelPosition!.width).toBeGreaterThan(1_300);

    const listMetrics = await panel.getByTestId("saved-stocks-landing-list").evaluate((element) => ({
      clientHeight: element.clientHeight,
      overflowY: getComputedStyle(element).overflowY,
      scrollHeight: element.scrollHeight,
    }));
    expect(listMetrics.overflowY).toBe("visible");
    expect(listMetrics.scrollHeight).toBeLessThanOrEqual(listMetrics.clientHeight);
  });

  test("saved rows expose quote provenance and stale state", async ({ page }) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-006", "Saved quote provenance");
    const now = new Date().toISOString();
    await page.addInitScript(({ key, timestamp }) => {
      window.localStorage.setItem(key, JSON.stringify({
        version: 1,
        items: [{ ticker: "AAPL", addedAt: timestamp, lastVisitedAt: timestamp, lastSection: "valuation" }],
      }));
    }, { key: STORAGE_KEY, timestamp: now });
    await page.route("**/api/stocks/snapshots?*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "success",
          as_of: now,
          warnings: [],
          data: [{
            ticker: "AAPL",
            company_name: "Apple Inc.",
            price: 210.5,
            change: -1.2,
            change_percent: -0.57,
            currency: "USD",
            status: "success",
            as_of: now,
            warnings: [],
            sources: [{
              provider: "Alpaca",
              source_url: "https://example.com/aapl",
              source_timestamp: now,
              fetched_at: now,
              is_stale: true,
            }],
          }],
        }),
      });
    });

    await page.goto("/");
    const panel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(panel.getByText(/Alpaca · stale ·/)).toBeVisible();
    await expect(panel.getByRole("link", { name: "View all saved" })).toBeVisible();
  });

  test("sync retry preserves visible data and clears transient errors", async ({ page, request }, testInfo) => {
    await labelSavedCase("VAL-E2E-SAVED-P0-004", "Saved stock sync recovery");
    const email = emailFor("saved-retry", testInfo.project.name);
    const password = "password123";

    await page.goto("/stocks/TSLA/news");
    await page.getByRole("button", { name: "Save TSLA to saved stocks" }).first().click();
    await request.post(`${FIXTURE_CONTROL_URL}/__test__/saved-stocks-fail-next`, {
      data: { email, merges: 1 },
    });

    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email, "/account");

    const panel = page.getByRole("region", { name: "Saved Stocks" });
    await expect(panel.getByText("TSLA", { exact: true })).toBeVisible();
    await expect(panel.locator('[role="alert"]')).toContainText("Your device copy was kept");
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).not.toBeNull();

    await panel.getByRole("button", { name: "Retry" }).click();
    await expect(panel.locator('[role="alert"]')).toHaveCount(0);
    await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();

    await request.post(`${FIXTURE_CONTROL_URL}/__test__/saved-stocks-fail-next`, {
      data: { email, reads: 10 },
    });
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(panel.getByText("TSLA", { exact: true })).toBeVisible();
    await expect(panel.locator('[role="alert"]')).toContainText("Saved stocks could not be loaded");

    await request.post(`${FIXTURE_CONTROL_URL}/__test__/saved-stocks-fail-next`, {
      data: { email, reads: 0 },
    });
    await panel.getByRole("button", { name: "Retry" }).click();
    await expect(panel.locator('[role="alert"]')).toHaveCount(0);
    await expect(panel.getByText("TSLA", { exact: true })).toBeVisible();
  });
});
