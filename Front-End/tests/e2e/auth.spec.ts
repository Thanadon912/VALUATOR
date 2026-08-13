import { expect, test } from "@playwright/test";
import { allure } from "allure-playwright";
import { confirmSignup, openPasswordRecovery } from "./auth-helpers";

const FIXTURE_CONTROL_URL = process.env.E2E_FIXTURE_CONTROL_URL || "http://127.0.0.1:8000";

function testEmail(prefix: string, projectName: string): string {
  return `${prefix}-${projectName.replace(/[^a-z0-9]/gi, "-")}-${Date.now()}@example.com`.toLowerCase();
}

async function labelAuthCase(id: string, story: string, priority: string = "P0", severity: string = "blocker") {
  await allure.epic("Authentication");
  await allure.feature("Authentication Lifecycle");
  await allure.story(story);
  await allure.layer("frontend-e2e");
  await allure.label("priority", priority);
  await allure.severity(severity);
  await allure.owner("Thanadon");
  await allure.testCaseId(id);
}

test.describe("Account authentication", () => {
  test("email registration, session refresh, logout, and email login", async ({ page, request }, testInfo) => {
    await labelAuthCase("VAL-E2E-AUTH-P0-001", "Email registration and login");
    const email = testEmail("auth", testInfo.project.name);
    const password = "password123";

    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Check your inbox")).toBeVisible();
    await confirmSignup(page, email, "/account");
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText(email)).toBeVisible();
    await expect(page.getByRole("button", { name: "Log out" }).first().locator("svg")).toBeVisible();
    await page.reload();
    await expect(page.getByText(email)).toBeVisible();

    await page.getByRole("button", { name: "Log out" }).first().click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("link", { name: "Sign up" })).toBeVisible();

    await page.goto("/login?next=https%3A%2F%2Fevil.example");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText("We couldn’t sign you in")).toBeVisible();

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);

    await expect.poll(async () => {
      const state = await request.post(`${FIXTURE_CONTROL_URL}/__test__/auth-email-state`, {
        data: { email },
      });
      return state.json();
    }).toEqual({ confirmed: true, welcome_deliveries: 1 });
  });

  test("unconfirmed email keeps the user and device data in place", async ({ page }, testInfo) => {
    await labelAuthCase("VAL-E2E-AUTH-P0-002", "Email confirmation pending");
    const email = testEmail("pending-confirmation", testInfo.project.name);

    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("password123");
    await page.getByLabel("Confirm Password").fill("password123");
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page).toHaveURL(/\/register/);
    await expect(page.getByText("Check your inbox")).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();
    await expect(page.getByRole("button", { name: "Use a different email" })).toBeVisible();
  });

  test("Google OAuth completes through the PKCE callback", async ({ page }) => {
    await labelAuthCase("VAL-E2E-AUTH-P0-003", "Google OAuth");

    await page.goto("/login?next=%2Faccount");
    await page.getByRole("button", { name: "Continue with Google" }).click();

    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByText("google-user@example.com")).toBeVisible();
    await expect(page.getByText("Google", { exact: true })).toBeVisible();
  });

  test("password recovery uses a generic request state and accepts a new password", async ({ page }, testInfo) => {
    await labelAuthCase("VAL-E2E-AUTH-P0-004", "Password recovery");
    const email = testEmail("recovery", testInfo.project.name);
    const originalPassword = "password123";
    const newPassword = "new-password-456";

    await page.goto("/register");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(originalPassword);
    await page.getByLabel("Confirm Password").fill(originalPassword);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email);
    await page.getByRole("button", { name: "Log out" }).first().click();

    const forgotPasswordResponse = await page.goto("/forgot-password");
    expect(forgotPasswordResponse?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "Reset password" })).toBeVisible();
    await page.getByLabel("Email").fill("wrong-address@example.com");
    await page.getByRole("button", { name: "Send reset link" }).click();
    await expect(page.getByText("Check your inbox")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send another link" })).toBeEnabled();
    await page.getByLabel("Email").fill(email);
    await page.getByRole("button", { name: "Send another link" }).click();
    await expect(page.getByText("Check your inbox")).toBeVisible();

    await openPasswordRecovery(page, email);
    await expect(page).toHaveURL(/\/account\/update-password$/);
    await page.getByLabel("New password", { exact: true }).fill(newPassword);
    await page.getByLabel("Confirm new password").fill(newPassword);
    await page.getByRole("button", { name: "Update password" }).click();

    await expect(page).toHaveURL(/\/login\?message=password_updated/);
    await expect(page.getByText("Password updated")).toBeVisible();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(newPassword);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("duplicate registration does not reveal whether the account exists", async ({ page }, testInfo) => {
    await labelAuthCase("VAL-E2E-AUTH-P0-006", "Duplicate email registration");
    const email = testEmail("duplicate", testInfo.project.name);
    const password = "password123";

    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();
    await confirmSignup(page, email, "/account");
    await page.getByRole("button", { name: "Log out" }).first().click();

    await page.goto("/register?next=%2Faccount");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByLabel("Confirm Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Check your inbox")).toBeVisible();
    await expect(page.getByText(/can receive a confirmation email/)).toBeVisible();
    await expect(page.getByText("This email already has an account")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Sign in", exact: true }).last()).toHaveAttribute("href", "/login?next=%2Faccount");
    await expect(page.getByRole("link", { name: "Reset password" })).toHaveAttribute("href", "/forgot-password?next=%2Faccount");
  });

  test("password reset rate limits are shown as retryable errors", async ({ page }) => {
    await labelAuthCase("VAL-E2E-AUTH-P1-007", "Password reset rate limit", "P1", "normal");

    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill("rate-limit@example.com");
    await page.getByRole("button", { name: "Send reset link" }).click();

    await expect(page.getByText("A link was requested recently")).toBeVisible();
    await expect(page.getByLabel("Email")).toBeEnabled();
    await expect(page.getByRole("button", { name: "Send reset link" })).toBeEnabled();
  });

  test("focused auth shell correctly manages layout, visibility, and validation feedback", async ({ page }) => {
    await labelAuthCase("VAL-E2E-AUTH-P1-005", "Auth shell layout and feedback regression", "P1", "normal");

    await page.goto("/login?next=%2Faccount");
    await expect(page.getByRole("link", { name: "Instrument" })).toBeHidden();
    await expect(page.getByRole("link", { name: "Methods" })).toBeHidden();
    await expect(page.getByRole("link", { name: "Sources" })).toBeHidden();

    await expect(page.getByRole("link", { name: "VALUATOR home" })).toHaveAttribute("href", "/");
    await expect(page.getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/register?next=%2Faccount");

    await page.goto("/register?next=%2Faccount");
    await expect(page.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", "/login?next=%2Faccount");
    await expect(page.getByRole("link", { name: "Sign up" })).toBeHidden();

    await page.getByLabel("Email").fill("invalid-email");
    const passwordInput = page.getByLabel("Password", { exact: true });
    await passwordInput.fill("short");

    await expect(passwordInput).toHaveAttribute("type", "password");
    const revealBtn = page.getByRole("button", { name: "Show password" }).first();

    const revealBox = await revealBtn.boundingBox();
    expect(revealBox!.height).toBeGreaterThanOrEqual(44);
    expect(revealBox!.width).toBeGreaterThanOrEqual(44);

    await revealBtn.focus();
    await revealBtn.press("Enter");
    await expect(passwordInput).toHaveAttribute("type", "text");
    await expect(passwordInput).toHaveValue("short");

    await expect(page.locator("form").first()).toHaveAttribute("novalidate", "");

    await page.getByRole("button", { name: "Create account" }).click();

    const emailInput = page.getByLabel("Email");
    await expect(emailInput).toHaveValue("invalid-email");
    await expect(emailInput).toHaveAttribute("aria-invalid", "true");

    await expect(passwordInput).toHaveAttribute("aria-invalid", "true");

    await expect(page.getByText("Enter a valid email address.")).toBeVisible();
    await expect(page.getByText("Use at least 8 characters.").last()).toBeVisible();
    await expect(emailInput).toBeFocused();

    const emailBox = await emailInput.boundingBox();
    expect(emailBox!.height).toBeGreaterThanOrEqual(44);

    const submitBox = await page.getByRole("button", { name: "Create account" }).boundingBox();
    expect(submitBox!.height).toBeGreaterThanOrEqual(44);

    const viewportSize = page.viewportSize();
    if (viewportSize) {
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(scrollWidth).toBeLessThanOrEqual(viewportSize.width);

      // Force mobile viewport to explicitly check mobile layout properties
      await page.setViewportSize({ width: 390, height: 844 });

      const mobileScrollHeight = await page.evaluate(() => document.documentElement.scrollHeight);
      expect(mobileScrollHeight).toBeLessThanOrEqual(844);

      const mobileScrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(mobileScrollWidth).toBeLessThanOrEqual(390);

      // Restore original viewport
      await page.setViewportSize(viewportSize);
    }
  });

  test("account route uses task navigation without landing-page anchors", async ({ page }) => {
    await labelAuthCase("VAL-E2E-AUTH-P1-006", "Account task navigation", "P1", "normal");

    await page.goto("/account");
    const navigation = page.getByRole("navigation", { name: "Account" });
    await expect(navigation.getByRole("link", { name: "New analysis" })).toHaveAttribute("href", "/#find-fair-value");
    await expect(navigation.getByRole("link", { name: "Account" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: "Instrument", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Methods", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Sources", exact: true })).toHaveCount(0);

    await page.setViewportSize({ width: 320, height: 800 });
    await expect(navigation.getByRole("link", { name: "New analysis" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  });

  test("account can return to the exact safe workspace and rejects unsafe return paths", async ({ page }) => {
    await page.goto("/account?returnTo=%2Fstocks%2FTSLA%2Fvaluation");
    await expect(page.getByRole("navigation", { name: "Account" }).getByRole("link", { name: "Back to TSLA valuation" }))
      .toHaveAttribute("href", "/stocks/TSLA/valuation");

    await page.goto("/account?returnTo=https%3A%2F%2Fevil.example");
    await expect(page.getByRole("navigation", { name: "Account" }).getByRole("link", { name: "New analysis" }))
      .toHaveAttribute("href", "/#find-fair-value");
  });

  test("a newer deployed revision is offered as an explicit reload", async ({ page }) => {
    await page.route("**/api/release", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ revision: "newer-e2e-revision" }),
    }));
    await page.goto("/");
    await expect(page.getByRole("status").filter({ hasText: "New version available" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reload now" })).toBeVisible();
  });
});
