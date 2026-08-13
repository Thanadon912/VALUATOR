import assert from "node:assert/strict"
import { chromium } from "playwright"

const BASE_URL = process.env.LANDING_SMOKE_URL || "http://127.0.0.1:3200"
const stages = [
  ["evidence", "Provider record"],
  ["assumptions", "Classification stays visible"],
  ["methods", "DCF uncertainty, made visible"],
  ["expectations", /Market expectations resolved|Solver result unavailable/],
]
const stageProgress = [0.1, 0.35, 0.6, 0.85]

async function scrollToSceneProgress(page, progress) {
  await page.evaluate(({ progress: targetProgress }) => {
    const target = document.querySelector("[data-instrument-scene]")
    if (!(target instanceof HTMLElement)) throw new Error("Instrument scene not found")
    const top = target.getBoundingClientRect().top + window.scrollY
    const travel = target.offsetHeight - window.innerHeight
    window.scrollTo({ top: top + travel * targetProgress, behavior: "instant" })
  }, { progress })
}

const browser = await chromium.launch({ headless: true })
const desktopViewport = { width: 1920, height: 1012 }
const page = await browser.newPage({ viewport: desktopViewport, deviceScaleFactor: 1 })
const consoleErrors = []

page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text())
})

try {
  const apiResponse = await page.request.get(`${BASE_URL}/api/featured-walkthrough`, { timeout: 100_000 })
  assert.equal(apiResponse.ok(), true, "featured walkthrough endpoint should return successfully")
  const payload = await apiResponse.json()
  assert.equal(payload.ticker, "MSFT")
  assert.ok(["complete", "partial"].includes(payload.status), "featured response must contain real engine data")
  assert.ok(Object.values(payload.engines).some((engine) => Number.isFinite(engine?.computed_fair_value)), "at least one engine must return a real fair value")

  await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 })
  const desktopInstrument = page.locator(".instrument-pinned .instrument-face")
  await desktopInstrument.getByText(/VALIDATED|PARTIAL/).waitFor({ state: "visible", timeout: 100_000 })

  const aaplLink = page.getByRole("link", { name: "AAPL", exact: true }).first()
  assert.equal(await aaplLink.getAttribute("href"), "/stocks/AAPL/valuation", "landing examples must open the valuation workspace")

  for (let index = 0; index < stages.length; index += 1) {
    const [, expectedHeading] = stages[index]
    await scrollToSceneProgress(page, stageProgress[index])
    await page.waitForTimeout(750)
    await desktopInstrument.getByText(expectedHeading).waitFor({ state: "visible", timeout: 10_000 })
    const footerBox = await desktopInstrument.locator("footer").boundingBox()
    assert.ok(footerBox, "instrument footer should be measurable")
    assert.ok(footerBox.y + footerBox.height <= desktopViewport.height, `instrument footer must remain inside the viewport at stage ${index + 1}`)
    await page.screenshot({ path: `/tmp/valuator-stage-${index + 1}.png`, fullPage: false })
  }

  const stageValue = desktopInstrument.locator("footer > div").first().locator("p").nth(1)
  await scrollToSceneProgress(page, 0.45)
  await page.waitForTimeout(400)
  assert.equal((await stageValue.innerText()).trim(), "2 / 4")
  for (const progress of [0.48, 0.5, 0.52]) {
    await scrollToSceneProgress(page, progress)
    await page.waitForTimeout(80)
    assert.equal((await stageValue.innerText()).trim(), "2 / 4", "forward hysteresis should prevent threshold thrashing")
  }
  await scrollToSceneProgress(page, 0.53)
  await page.waitForTimeout(120)
  assert.equal((await stageValue.innerText()).trim(), "3 / 4")
  for (const progress of [0.52, 0.5, 0.48]) {
    await scrollToSceneProgress(page, progress)
    await page.waitForTimeout(80)
    assert.equal((await stageValue.innerText()).trim(), "3 / 4", "reverse hysteresis should prevent threshold thrashing")
  }
  await scrollToSceneProgress(page, 0.47)
  await page.waitForTimeout(120)
  assert.equal((await stageValue.innerText()).trim(), "2 / 4")

  const body = await page.locator("body").innerText()
  assert.doesNotMatch(body, /Awaiting a validated ticker/i)
  assert.doesNotMatch(body, /Evidence\s+Pending|Model range\s+Pending|Expectations\s+Pending/i)
  assert.equal(consoleErrors.length, 0, `unexpected console errors: ${consoleErrors.join(" | ")}`)

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 })
  await mobilePage.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 })
  const finalMobileStage = mobilePage.locator('[data-instrument-stage="expectations"]')
  await finalMobileStage.scrollIntoViewIfNeeded()
  await finalMobileStage.getByText(/Market expectations resolved|Solver result unavailable/).waitFor({ state: "visible", timeout: 100_000 })
  const mobileOverflow = await mobilePage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  assert.ok(mobileOverflow <= 1, `mobile layout must not overflow horizontally (${mobileOverflow}px)`)
  await mobilePage.screenshot({ path: "/tmp/valuator-stage-4-mobile.png", fullPage: false })
  await mobilePage.close()

  const reducedMotionPage = await browser.newPage({ viewport: desktopViewport, reducedMotion: "reduce" })
  await reducedMotionPage.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 30_000 })
  await reducedMotionPage.locator(".instrument-pinned .instrument-face").getByText(/VALIDATED|PARTIAL/).waitFor({ state: "visible", timeout: 100_000 })
  await scrollToSceneProgress(reducedMotionPage, 0.6)
  await reducedMotionPage.locator(".instrument-pinned .instrument-face").getByText("DCF uncertainty, made visible").waitFor({ state: "visible", timeout: 10_000 })
  await reducedMotionPage.close()

  console.log("Landing featured walkthrough smoke passed")
} finally {
  await browser.close()
}
