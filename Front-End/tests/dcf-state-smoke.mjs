import assert from "node:assert/strict";
import { chromium } from "playwright";

const APP_URL = process.env.DCF_SMOKE_URL || "http://127.0.0.1:3200/stocks/MSFT/dcf";

async function fillBaseInputs(page) {
  await page.locator("label").filter({ hasText: /^WACC/ }).first().locator("input").fill("8.50");
  await page
    .locator("label")
    .filter({ hasText: /^Terminal Growth Rate/ })
    .locator("input")
    .fill("2.50");
  await page.locator("label").filter({ hasText: /^Total Cash & Investments/ }).locator("input").fill("80");
  await page.locator("label").filter({ hasText: /^Debt/ }).locator("input").fill("50");
  await page
    .locator("label")
    .filter({ hasText: /^Change in NWC as % of Revenue/ })
    .locator("input")
    .fill("5");
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  let lastDcfPayload = null;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/api/stocks/MSFT/dcf")) {
      lastDcfPayload = JSON.parse(request.postData() || "{}");
    }
  });
  await page.goto(new URL(APP_URL).origin, { waitUntil: "networkidle" });
  await page.evaluate(() => window.localStorage.clear());
  await page.goto(APP_URL, { waitUntil: "networkidle" });
  assert.match(await page.locator("body").innerText(), /Use 5Y Median/, "Margin target actions are visible");
  assert.match(await page.locator("body").innerText(), /Severity Summary/, "Warning severity summary is visible");
  assert.match(await page.locator("body").innerText(), /Errors · .*High-Risk Warnings · .*Review Items/, "Warning summary groups messages by severity");

  const scenarioButtons = page.locator(".dcf-toolbar .segmented-control").nth(1).locator("button");
  const bearButton = scenarioButtons.nth(0);
  const bullButton = scenarioButtons.nth(2);

  assert.equal(await bearButton.isDisabled(), true, "Bear is locked before Base calculation");
  assert.equal(await bullButton.isDisabled(), true, "Bull is locked before Base calculation");

  await fillBaseInputs(page);
  await page.getByRole("button", { name: "Calculate Base" }).click();
  await page.waitForFunction(
    () =>
      document.body.innerText.includes("Base Fair Value") &&
      document.body.innerText.includes("Apply Changes & Recalculate Base"),
    null,
    {
      timeout: 15000,
    },
  );

  assert.equal(await bearButton.isDisabled(), false, "Bear unlocks after Base calculation");
  assert.equal(await bullButton.isDisabled(), false, "Bull unlocks after Base calculation");
  const baseCalculatedText = await page.locator("body").innerText();
  assert.match(baseCalculatedText, /Calculated/, "Header reflects calculated state");
  assert.doesNotMatch(
    baseCalculatedText,
    /Ready To Calculate/,
    "Header does not say Ready To Calculate when result is current",
  );

  await bullButton.click();
  assert.match(
    await page.locator("body").innerText(),
    /Create Bull case from the current Base snapshot/,
    "Bull opens in create-from-base state",
  );
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /Base Case Inputs/,
    "Bull tab does not render Base Case Inputs",
  );

  await page.getByRole("button", { name: "Create Bull From Base" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("Bull Case Inputs"));
  assert.match(await page.locator("body").innerText(), /Calculate Bull/, "Bull action label is scenario-aware");
  assert.match(await page.locator("body").innerText(), /Bull Fair Value/, "Bull result title is scenario-aware");
  assert.match(
    await page.locator("body").innerText(),
    /Bull is currently identical to Base/,
    "Copied Bull scenario is flagged until a material assumption changes",
  );

  await page.getByRole("button", { name: "Advanced" }).click();
  await page.getByText("Detailed Equity Bridge Adjustments", { exact: true }).click();
  assert.match(
    await page.locator("body").innerText(),
    /Marketable Securities - Not Reviewed/,
    "Optional adjustments start as not reviewed, not silent zero",
  );
  await page.getByLabel("Revenue Growth Year 1").fill("3.00");
  await page
    .locator("label")
    .filter({ hasText: /^Marketable Securities/ })
    .locator("input")
    .fill("0.00");
  await page.getByText("SBC, Dilution, and Normalization", { exact: true }).click();
  await page
    .locator("label")
    .filter({ hasText: /^Revenue Normalization Adjustment/ })
    .locator("input")
    .fill("10.00");
  assert.match(
    await page.locator("body").innerText(),
    /Marketable Securities - Confirmed Zero/,
    "Explicit zero is distinguished from not reviewed",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Effective starting revenue: \$260B/,
    "Revenue normalization updates effective starting revenue without overwriting reported revenue",
  );

  await scenarioButtons.nth(1).click();
  const baseYearOneGrowth = await page.getByLabel("Revenue Growth Year 1").inputValue();
  assert.notEqual(baseYearOneGrowth, "3.00", "Editing Bull yearly drivers does not mutate Base arrays");

  await bullButton.click();
  const bullYearOneGrowth = await page.getByLabel("Revenue Growth Year 1").inputValue();
  assert.equal(bullYearOneGrowth, "3.00", "Bull keeps its independent yearly driver value");
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /Bull is currently identical to Base/,
    "Bull identical warning clears after a material assumption changes",
  );
  await page.waitForFunction(() => {
    const raw = window.localStorage.getItem("usa-dcf:MSFT:all-scenarios:phase-c-v1");
    if (!raw) return false;
    const draft = JSON.parse(raw);
    return (
      draft.mode === "advanced" &&
      draft.scenarioKey === "bull" &&
      draft.scenarios?.bull?.advancedDrivers?.revenueGrowthByYear?.[0] === "3.00" &&
      draft.scenarios?.bull?.inputs?.marketableSecurities === "0.00"
    );
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.body.innerText.includes("Bull Year-by-Year Model"));
  assert.match(await page.locator("body").innerText(), /Draft (restored|autosaved)/, "Reload keeps draft persistence active");
  await page.getByText("Detailed Equity Bridge Adjustments", { exact: true }).click();
  assert.match(await page.locator("body").innerText(), /Marketable Securities - Confirmed Zero/, "Reload preserves optional adjustment review state");
  assert.equal(
    await page.getByLabel("Revenue Growth Year 1").inputValue(),
    "3.00",
    "Reload preserves Bull yearly driver edits",
  );

  await page.getByRole("button", { name: "Basic" }).click();
  await page
    .locator("label")
    .filter({ hasText: /^Required Operating Cash/ })
    .locator("input")
    .fill("10.00");
  assert.match(
    await page.locator("body").innerText(),
    /Cash included in equity bridge: \$70B/,
    "Required operating cash reduces cash included in equity bridge",
  );
  await page.locator("label").filter({ hasText: /^Manual Current Price/ }).locator("input").fill("300");
  assert.match(
    await page.locator("body").innerText(),
    /User override status: User Override/,
    "Manual current price override status is explicit",
  );

  await page.locator("label").filter({ hasText: /^Revenue Growth/ }).locator("input").fill("3.00");
  await page.getByRole("button", { name: "Calculate Bull" }).click();
  await page.waitForFunction(
    () =>
      document.body.innerText.includes("Bull Current Valuation Snapshot") &&
      document.body.innerText.includes("Apply Changes & Recalculate Bull"),
    null,
    {
    timeout: 15000,
    },
  );
  assert.match(
    await page.locator("body").innerText(),
    /Bull Current Valuation Snapshot/,
    "Bull valuation snapshot uses active scenario",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Manual Quote/,
    "Manual current price unlocks upside/downside without blocking intrinsic value",
  );
  assert.equal(
    lastDcfPayload?.equity_bridge?.cash_and_equivalents?.value,
    70_000_000_000,
    "DCF payload sends excess cash after required operating cash deduction",
  );
  assert.equal(
    lastDcfPayload?.normalization_adjustments?.[0]?.value,
    10_000_000_000,
    "DCF payload sends starting revenue normalization separately from reported revenue",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Terminal Value \/ EV/i,
    "Terminal concentration badge is visible after calculation",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Terminal Economics:/i,
    "Terminal economics summary is visible after calculation",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Terminal Value Dependence|Valuation Engine Warning/,
    "Warning summary surfaces high-risk valuation issues without relying on same-color warning blocks",
  );
  assert.match(
    await page.locator("body").innerText(),
    /WACC x Terminal Growth/,
    "DCF page renders a WACC by terminal growth sensitivity matrix",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Revenue Growth x EBIT Margin/,
    "DCF page renders a revenue growth by EBIT margin sensitivity matrix",
  );
  await page.getByRole("button", { name: "Advanced" }).click();
  await page.waitForFunction(() => document.body.innerText.includes("Bull Year-by-Year Model"));
  assert.match(await page.locator("body").innerText(), /Forecast Drivers/, "Advanced step navigation is visible");
  assert.match(await page.locator("body").innerText(), /Adjustments\s+Not Reviewed|Adjustments\s+Reviewed/, "Advanced section badges summarize review state");
  assert.equal(
    await page.locator(".dcf-toolbar").evaluate((element) => getComputedStyle(element).position),
    "sticky",
    "Scenario toolbar stays sticky while editing long Advanced sections",
  );
  assert.match(
    await page.locator(".dcf-toolbar-context").innerText(),
    /Advanced\s+Bull/i,
    "Sticky toolbar shows the active mode and scenario",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Mathematically reconciled|Economically Requires Review/,
    "Forecast worksheet separates mathematical reconciliation from economic review",
  );
  await page.getByText("Reinvestment and WACC", { exact: true }).click();
  assert.match(
    await page.locator("body").innerText(),
    /WACC Component Sources/,
    "WACC builder shows component source guardrails",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Debt weight is a capital-structure assumption/i,
    "WACC builder states debt weight is separate from bridge debt",
  );
  await page.getByText("SBC, Dilution, and Normalization", { exact: true }).click();
  assert.match(
    await page.locator("body").innerText(),
    /SBC Treatment Reconciliation/,
    "Advanced mode shows SBC treatment reconciliation",
  );
  assert.match(
    await page.locator("body").innerText(),
    /No SBC add-back or share dilution path is sent to the engine/,
    "Expense SBC treatment does not imply hidden add-back or dilution",
  );
  await page.getByText("Terminal Value and Equity Bridge Inputs", { exact: true }).click();
  await page.getByText("Source Lineage", { exact: true }).scrollIntoViewIfNeeded();
  assert.equal(await page.locator(".dcf-toolbar").isVisible(), true, "Sticky scenario toolbar remains visible near the bottom");
  assert.match(
    await page.locator("body").innerText(),
    /Bull - Compact Bridge/,
    "Advanced editable sections include the active scenario name",
  );
  await page.getByRole("button", { name: "Basic" }).click();

  await page.locator("label").filter({ hasText: /^WACC/ }).first().locator("input").fill("9.00");
  assert.match(
    await page.locator("body").innerText(),
    /Recalculation Required/,
    "Editing a calculated scenario marks result stale",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Previous Calculation/,
    "Stale valuation labels prior output as previous calculation",
  );

  await scenarioButtons.nth(1).click();
  const baseGrowth = await page
    .locator("label")
    .filter({ hasText: /^Revenue Growth/ })
    .locator("input")
    .inputValue();
  assert.notEqual(baseGrowth, "3.00", "Editing Bull does not mutate Base assumptions");

  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /Missing component: TTM change in NWC/,
    "Manual NWC removes stale missing-component warning",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Historical TTM FCFF Evidence/i,
    "Historical TTM FCFF evidence is labeled separately",
  );
  assert.match(
    await page.locator("body").innerText(),
    /Effective Year 0 conversion for reference:/,
    "Manual NWC ratio displays converted monetary amount",
  );
  await page.getByRole("button", { name: "Advanced" }).click();
  assert.match(await page.locator("body").innerText(), /Editable Driver/, "Advanced worksheet shows cell role legend");
  assert.match(await page.locator("body").innerText(), /Currency: USD/, "Advanced worksheet shows unit metadata");
} finally {
  await browser.close();
}
