import { test, expect } from "@playwright/test";
import { allure } from "allure-playwright";

test.describe("Summary Dashboard Resilience", () => {
  test("missing modules do not crash the page and display unavailable states", async ({ page }) => {
    await allure.epic("Summary & Fundamentals");
    await allure.feature("Summary Dashboard");
    await allure.story("Resilience to Missing Modules");
    await allure.layer("frontend-e2e");
    await allure.label("priority", "P0");
    await allure.severity("normal");
    await allure.owner("Thanadon");
    await allure.testCaseId("VAL-E2E-P0-004");

    // We use the MISSING fixture route which omits quote, price_history, key_facts
    await page.goto("/stocks/MISSING/summary");

    // Wait for the workspace header to show it loaded
    await expect(page.getByRole("heading", { name: /Tesla, Inc\.|MISSING/ }).first()).toBeVisible();

    // Verify no Next.js crash boundary
    await expect(page.getByText("This page couldn’t load")).not.toBeVisible();

    // Verify unavailable states for modules that render ModuleState or EmptyPanel
    await expect(page.getByText("Price history is unavailable from the current provider.").first()).toBeVisible();
    
    // Quote is handled differently in the header (shows '—' for missing numbers)
    await expect(page.getByText("— (—)").first()).toBeVisible();
  });

  test("real numeric zeros are not converted to missing or unavailable states", async ({ page }) => {
    await allure.epic("Summary & Fundamentals");
    await allure.feature("Summary Dashboard");
    await allure.story("Zero Value Handling");
    await allure.layer("frontend-e2e");
    await allure.label("priority", "P0");
    await allure.severity("normal");
    await allure.owner("Thanadon");
    await allure.testCaseId("VAL-E2E-P0-005");

    // We use the ZERO fixture route which forces quote data to zero
    await page.goto("/stocks/ZERO/summary");

    await expect(page.getByRole("heading", { name: /Tesla, Inc\.|ZERO/ }).first()).toBeVisible();

    // Wait for the specific quote card section
    // If it's a real 0, we shouldn't see 'unavailable' or '--' for the price
    // Since quote(ticker, 0) is passed, we should see $0.00
    await expect(page.getByText("$0.00", { exact: true }).first()).toBeVisible();
  });
});

