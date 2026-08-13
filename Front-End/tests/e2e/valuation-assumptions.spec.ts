import { expect, test } from "@playwright/test";
import { allure } from "allure-playwright";
import { confirmSignup } from "./auth-helpers";

const STORAGE_KEY = "valuator:valuation-assumptions:v1";
const FIXTURE_CONTROL_URL = process.env.E2E_FIXTURE_CONTROL_URL ?? "http://127.0.0.1:8300";

async function labelCase(id: string, story: string) {
  await allure.epic("Instrument Workspace");
  await allure.feature("Valuation Assumptions");
  await allure.story(story);
  await allure.layer("frontend-e2e");
  await allure.label("priority", "P0");
  await allure.severity("blocker");
  await allure.owner("Thanadon");
  await allure.testCaseId(id);
}

function emailFor(prefix: string, projectName: string) {
  return `${prefix}-${projectName.replace(/[^a-z0-9]/gi, "-")}-${Date.now()}@example.com`.toLowerCase();
}

async function openAssumptions(page: import("@playwright/test").Page) {
  const toggle = page.getByRole("button", { name: /DCF assumptions/i });
  if (await toggle.getAttribute("aria-expanded") === "false") await toggle.click();
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toBeVisible();
}

async function applyCustomAssumptions(page: import("@playwright/test").Page) {
  await openAssumptions(page);
  await page.getByLabel("Stage 1 growth", { exact: true }).fill("12.5");
  await page.getByLabel("Perpetual growth", { exact: true }).fill("2.5");
  await page.getByLabel(/Discount rate/).fill("8.5");
  await page.getByRole("button", { name: "Apply to workspace" }).click();
}

test("guest assumptions survive refresh and reset cleanly", async ({ page }) => {
  await labelCase("VAL-E2E-ASSUMPTIONS-P0-001", "Guest persistence");
  await page.goto("/stocks/TSLA/valuation");
  await expect(page.getByRole("heading", { name: "Compare valuation methods" })).toBeVisible();
  await applyCustomAssumptions(page);

  await expect(page.getByText("Saved on this device", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).not.toBeNull();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Compare valuation methods" })).toBeVisible();
  await openAssumptions(page);
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("12.5");
  await expect(page.getByLabel("Perpetual growth", { exact: true })).toHaveValue("2.5");
  await expect(page.getByLabel(/Discount rate/)).toHaveValue("8.5");

  await page.getByRole("button", { name: "Reset all" }).click();
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("10");
  await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();
});

test("guest assumptions merge into one account and remain isolated", async ({ page, browser }, testInfo) => {
  await labelCase("VAL-E2E-ASSUMPTIONS-P0-002", "Account sync and isolation");
  const password = "password123";
  const ownerEmail = emailFor("assumption-owner", testInfo.project.name);

  await page.goto("/stocks/TSLA/valuation");
  await expect(page.getByRole("heading", { name: "Compare valuation methods" })).toBeVisible();
  await applyCustomAssumptions(page);
  await expect(page.getByText("Saved on this device", { exact: true })).toBeVisible();

  await page.goto("/register?next=%2Fstocks%2FTSLA%2Fvaluation");
  await page.getByLabel("Email").fill(ownerEmail);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await confirmSignup(page, ownerEmail, "/stocks/TSLA/valuation");
  await expect(page).toHaveURL(/\/stocks\/TSLA\/valuation$/);
  await expect(page.getByText("Saved to account", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate((key) => window.localStorage.getItem(key), STORAGE_KEY)).toBeNull();

  await page.reload();
  await openAssumptions(page);
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("12.5");
  await expect(page.getByText("Saved to account", { exact: true })).toBeVisible();

  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  const otherEmail = emailFor("assumption-other", testInfo.project.name);
  await otherPage.goto("/register?next=%2Fstocks%2FTSLA%2Fvaluation");
  await otherPage.getByLabel("Email").fill(otherEmail);
  await otherPage.getByLabel("Password", { exact: true }).fill(password);
  await otherPage.getByLabel("Confirm Password").fill(password);
  await otherPage.getByRole("button", { name: "Create account" }).click();
  await confirmSignup(otherPage, otherEmail, "/stocks/TSLA/valuation");
  await expect(otherPage).toHaveURL(/\/stocks\/TSLA\/valuation$/);
  await openAssumptions(otherPage);
  await expect(otherPage.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("10");
  await otherContext.close();

  await page.getByRole("button", { name: "Reset all" }).click();
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("10");
  await page.reload();
  await openAssumptions(page);
  await expect(page.getByLabel("Stage 1 growth", { exact: true })).toHaveValue("10");
});

test("temporary account read failure preserves authenticated mode and active defaults", async ({ page, request }, testInfo) => {
  await labelCase("VAL-E2E-ASSUMPTIONS-P0-003", "Account sync recovery");
  const password = "password123";
  const email = emailFor("assumption-read-recovery", testInfo.project.name);

  await page.goto("/register?next=%2Fstocks%2FTSLA%2Fvaluation");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await confirmSignup(page, email, "/stocks/TSLA/valuation");
  await expect(page).toHaveURL(/\/stocks\/TSLA\/valuation$/);

  await request.post(`${FIXTURE_CONTROL_URL}/__test__/valuation-assumptions-fail-next`, {
    data: { email, reads: 20 },
  });
  await page.reload();
  await expect(page.getByRole("link", { name: "Account" })).toBeVisible();
  await openAssumptions(page);
  await expect(page.getByText(/Account sync is temporarily unavailable/)).toBeVisible();
  await expect(page.getByText("Model defaults", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply to workspace" })).toBeDisabled();
});
