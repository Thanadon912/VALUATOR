import assert from "node:assert/strict";
import { chromium } from "playwright";

const BASE_URL = process.env.NEWS_SMOKE_BASE_URL || "http://127.0.0.1:3200";
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: "no-preference" });
const consoleErrors = [];

page.on("console", (message) => {
  if (message.type() === "error" && !message.text().includes("React DevTools")) {
    consoleErrors.push(message.text());
  }
});

try {
  await page.goto(`${BASE_URL}/stocks/MSFT/news`, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.getByRole("heading", { name: "Coverage snapshot" }).waitFor({ timeout: 60_000 });

  const body = await page.locator("body").innerText();
  assert.match(body, /MSFT news intelligence/i);
  assert.match(body, /Provider feed/i);
  assert.match(body, /App-derived/i);
  assert.doesNotMatch(body, /What to Watch|View all catalysts|upcoming catalysts/i);
  assert.doesNotMatch(body, /Market Pulse|Relevance to MSFT/i);

  await page.getByText("How derived cues work", { exact: true }).click();
  await page.getByText(/bounded keyword matching/i).waitFor({ state: "visible" });

  const firstArticle = page.locator("article").first();
  const saveButton = firstArticle.getByRole("button", { name: /^Save / });
  await saveButton.click();
  const removeButton = firstArticle.getByRole("button", { name: /^Remove / });
  await removeButton.waitFor({ state: "visible" });
  assert.equal(await removeButton.getAttribute("aria-pressed"), "true", "Bookmark must acknowledge its saved state");
  const storedBookmarks = await page.evaluate(() => window.localStorage.getItem("valuator:news-bookmarks:MSFT"));
  assert.ok(storedBookmarks && JSON.parse(storedBookmarks).length >= 1, "Bookmarks must persist in local storage");

  const initialArticleCount = await page.locator("article").count();
  const showMore = page.getByRole("button", { name: /Show \d+ more stories/i });
  if (await showMore.count()) {
    await showMore.click();
    assert.ok(await page.locator("article").count() > initialArticleCount, "Show more must reveal additional stories");
  }

  await page.screenshot({ path: "/tmp/news-dashboard-desktop.png", fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });

  const viewport = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert.ok(
    viewport.scrollWidth <= viewport.clientWidth,
    `News dashboard must not overflow at 390px (${viewport.scrollWidth} > ${viewport.clientWidth})`,
  );

  const firstHeadline = page.locator("article h3").first();
  await firstHeadline.waitFor({ state: "visible" });
  const headlineBox = await firstHeadline.boundingBox();
  assert.ok(headlineBox && headlineBox.x >= 0 && headlineBox.x + headlineBox.width <= 390, "Mobile headline must remain in view");

  const mobileIconTargets = await page.locator('article button[aria-label], article a[aria-label]').evaluateAll((elements) =>
    elements.slice(0, 4).map((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  assert.ok(
    mobileIconTargets.length > 0 && mobileIconTargets.every((target) => target.width >= 44 && target.height >= 44),
    `Mobile article actions must be at least 44x44px (${JSON.stringify(mobileIconTargets)})`,
  );

  await page.screenshot({ path: "/tmp/news-dashboard-mobile.png", fullPage: false });
  assert.equal(consoleErrors.length, 0, `Unexpected browser console errors: ${consoleErrors.join(" | ")}`);
  console.log("News dashboard production smoke passed");
} finally {
  await browser.close();
}
