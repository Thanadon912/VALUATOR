import { expect, test } from "@playwright/test";
import { allure } from "allure-playwright";

test.describe("News Dashboard", () => {
  test("news filtering and ticker consistency", async ({ page }) => {
    await allure.epic("News & Evidence");
    await allure.feature("News Dashboard");
    await allure.story("News Filtering and Consistency");
    await allure.layer("frontend-e2e");
    await allure.label("priority", "P0");
    await allure.severity("critical");
    await allure.owner("Thanadon");
    await allure.testCaseId("VAL-E2E-P0-002");

    // Mock the news API
    await page.route("**/api/stocks/TSLA/news", async (route) => {
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
            }
          ]
        })
      });
    });

    await page.goto("/stocks/TSLA/news");
    
    // Verify the ticker is correct in the header
    await expect(page.getByRole("heading", { name: "TSLA news intelligence" })).toBeVisible();
    
    // Verify articles are rendered
    await expect(page.getByRole("heading", { name: "Tesla beats earnings estimates" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tesla announces new factory" })).toBeVisible();
    
    // Verify filtering (e.g., search or topic)
    await page.getByPlaceholder("Search headlines, summaries, or sources").fill("earnings");
    await expect(page.getByRole("heading", { name: "Tesla announces new factory" })).not.toBeVisible();
    await expect(page.getByRole("heading", { name: "Tesla beats earnings estimates" })).toBeVisible();

    await page.getByPlaceholder("Search headlines, summaries, or sources").fill("");
    await page.getByRole("button", { name: "Save Tesla beats earnings estimates" }).click();
    await page.getByRole("button", { name: /^Saved\s+1$/ }).click();
    await expect(page.locator("article")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "Tesla beats earnings estimates" })).toBeVisible();
    await expect(page.getByText("The lead story is the only match for these filters.")).toHaveCount(0);

    await page.getByRole("button", { name: "Reset" }).click();
    await page.getByRole("button", { name: "Save Tesla announces new factory" }).click();
    await page.getByRole("button", { name: /^Saved\s+2$/ }).click();
    await expect(page.locator("article")).toHaveCount(2);
    await expect(page.getByRole("heading", { name: "Tesla beats earnings estimates" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tesla announces new factory" })).toBeVisible();
  });
});

test.describe("Evidence Traceability", () => {
  test("source links exist and are accessible for key metrics", async ({ page }) => {
    await allure.epic("News & Evidence");
    await allure.feature("Valuation Evidence");
    await allure.story("Source Traceability");
    await allure.layer("frontend-e2e");
    await allure.label("priority", "P0");
    await allure.severity("critical");
    await allure.owner("Thanadon");
    await allure.testCaseId("VAL-E2E-P0-003");

    // Mock valuation API to return telemetry sources
    await page.route("**/api/v1/valuation/dcf?ticker=AAPL", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ticker: "AAPL",
          valuation_status: "CALCULATED",
          valuation_methodology: "Standard Driver-Based DCF",
          engine_metadata: {},
          projections: [],
          monte_carlo_results: {},
          implied_expectations: {},
          current_price: 150,
          computed_fair_value: 100,
          underlying_assumptions: { 
            telemetry: { 
              market_cap: 2e12,
              risk_free_rate: 0.045,
              risk_free_rate_source: "https://treasury.gov/rfr",
              beta: 1.1,
              beta_source: "https://example.com/beta"
            } 
          }
        })
      });
    });

    await page.goto("/stocks/AAPL/valuation");
    
    // Verify the source link is rendered in the UI (since the test mocks an http URL, it renders as an <a> tag)
    const rfrLink = page.locator('a[href="https://treasury.gov/rfr"]');
    await expect(rfrLink).toBeVisible();
    await expect(rfrLink).toHaveText(/4\.5%/);
    
    const betaLink = page.locator('a[href="https://example.com/beta"]');
    await expect(betaLink).toBeVisible();
    await expect(betaLink).toHaveText(/1\.10/);
  });
});
