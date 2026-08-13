import { expect, test } from "@playwright/test";

const tickers = (process.env.LIVE_E2E_TICKERS ?? "TSLA,JPM,XOM,WMT")
  .split(",")
  .map((ticker) => ticker.trim().toUpperCase())
  .filter(Boolean);

function expectRelative(actual: number, expected: number, tolerance = 1e-7) {
  const relativeError = Math.abs(actual - expected) / Math.max(1, Math.abs(expected));
  expect(relativeError).toBeLessThan(tolerance);
}

test.describe("@live VALUATOR provider integration", () => {
  test.describe.configure({ mode: "serial", timeout: 240_000 });

  for (const ticker of tickers) {
    test(`${ticker} returns a source-aware DCF contract and renders its workspace`, async ({ page, request }) => {
      const response = await request.get(`/api/v1/valuation/dcf?ticker=${ticker}`, { timeout: 180_000 });
      expect(response.ok()).toBeTruthy();
      const payload = await response.json();

      for (const key of [
        "ticker",
        "timestamp",
        "current_price",
        "computed_fair_value",
        "valuation_status",
        "margin_of_safety_percentage",
        "valuation_methodology",
        "engine_metadata",
        "projections",
        "monte_carlo_results",
        "implied_expectations",
        "underlying_assumptions",
      ]) {
        expect(payload).toHaveProperty(key);
      }

      if (payload.valuation_status === "CALCULATED") {
        expect(Number.isFinite(payload.computed_fair_value)).toBeTruthy();
        expect(Array.isArray(payload.projections)).toBeTruthy();
        expect(payload.projections.length).toBeGreaterThan(0);
        const assumptions = payload.underlying_assumptions;
        const discountRate = payload.valuation_methodology === "Regulatory FCFE"
          ? assumptions.cost_of_equity ?? assumptions.discount_rate
          : assumptions.discount_rate ?? assumptions.wacc;
        const projectedCashFlows = payload.projections.map((row: Record<string, number>) =>
          payload.valuation_methodology === "Regulatory FCFE"
            ? row.free_cash_flow_to_equity
            : row.unlevered_free_cash_flow,
        );
        const presentValueCashFlows = projectedCashFlows.reduce(
          (sum: number, cashFlow: number, index: number) => sum + cashFlow / Math.pow(1 + discountRate, index + 1),
          0,
        );
        const presentValueTerminal = assumptions.terminal_value
          / Math.pow(1 + discountRate, projectedCashFlows.length);
        if (payload.valuation_methodology === "Regulatory FCFE") {
          expectRelative(
            payload.computed_fair_value,
            (presentValueCashFlows + presentValueTerminal) / assumptions.shares_outstanding,
          );
        } else {
          const enterpriseValue = presentValueCashFlows + presentValueTerminal;
          const equityValue = enterpriseValue - assumptions.total_debt + assumptions.cash;
          expectRelative(assumptions.enterprise_value, enterpriseValue);
          expectRelative(payload.computed_fair_value, equityValue / assumptions.shares_outstanding);
          if (assumptions.wacc_basis === "true_wacc_market_cap_debt_interest_tax") {
            const components = assumptions.wacc_components;
            expectRelative(
              assumptions.wacc,
              components.weight_equity * components.cost_of_equity
                + components.weight_debt * components.cost_of_debt_after_tax,
            );
          }
        }

        if (payload.monte_carlo_results?.iteration_count != null) {
          expect(payload.monte_carlo_results.iteration_count).toBe(10_000);
          expect(payload.monte_carlo_results.valid_sample_count).toBe(10_000);
          expect(payload.monte_carlo_results.bear_p10).toBeLessThanOrEqual(payload.monte_carlo_results.base_p50);
          expect(payload.monte_carlo_results.base_p50).toBeLessThanOrEqual(payload.monte_carlo_results.bull_p90);
          expect(
            payload.monte_carlo_results.histogram_bins.reduce(
              (sum: number, bin: { count: number }) => sum + bin.count,
              0,
            ),
          ).toBe(10_000);
        } else {
          expect(payload.underlying_assumptions.computational_warnings.join(" ")).toMatch(
            /Monte Carlo unavailable: insufficient comparable annual history/,
          );
        }
      } else {
        expect(payload.underlying_assumptions?.calculation_basis ?? "").toMatch(/missing|invalid/i);
      }

      await page.goto(`/stocks/${ticker}/valuation`, { waitUntil: "domcontentloaded", timeout: 180_000 });
      await expect(page.getByRole("tab", { name: "Valuation Overview" })).toBeVisible({ timeout: 120_000 });
      await expect(page.getByRole("tab", { name: "DCF Intrinsic Deep-Dive" })).toBeVisible();
      await expect(page.getByRole("tab", { name: "Simulation & Market Expectations" })).toBeVisible();
      const body = await page.locator("body").innerText();
      expect(body).not.toMatch(/\bNaN\b|\bInfinity\b|Engine Failure|API error 5\d\d/i);
    });
  }

  test("representative overview engines reconstruct from sourced inputs", async ({ request }) => {
    const asset = await (await request.get("/api/v1/valuation/asset-based?ticker=TSLA", { timeout: 180_000 })).json();
    expect(asset.valuation_status).toBe("CALCULATED");
    const assetInputs = asset.underlying_assumptions;
    const nav = assetInputs.total_assets - assetInputs.total_liabilities;
    const tangibleNav = nav - assetInputs.goodwill - assetInputs.intangible_assets;
    expectRelative(assetInputs.nav, nav);
    expectRelative(assetInputs.tangible_nav, tangibleNav);
    expectRelative(asset.computed_fair_value, assetInputs.tangible_net_net_per_share);

    const ddm = await (await request.get("/api/v1/valuation/ddm?ticker=KO", { timeout: 180_000 })).json();
    expect(ddm.valuation_status).toBe("APPLICABLE");
    const ddmInputs = ddm.underlying_assumptions;
    expectRelative(
      ddm.computed_fair_value,
      ddmInputs.annual_dividend_per_share * (1 + ddmInputs.dividend_growth_cagr)
        / (ddmInputs.cost_of_equity - ddmInputs.dividend_growth_cagr),
    );

    const relative = await (await request.get("/api/v1/valuation/relative?ticker=TSLA", { timeout: 180_000 })).json();
    expect(relative.valuation_status).toBe("CALCULATED");
    const relativeInputs = relative.underlying_assumptions;
    const impliedValues = [relativeInputs.fv_pe, relativeInputs.fv_pb, relativeInputs.fv_ev_ebitda]
      .filter((value: unknown): value is number => typeof value === "number" && value > 0);
    expectRelative(
      relative.computed_fair_value,
      impliedValues.reduce((sum: number, value: number) => sum + value, 0) / impliedValues.length,
    );

    const residual = await (await request.get("/api/v1/valuation/residual-income?ticker=JPM", { timeout: 180_000 })).json();
    expect(residual.valuation_status).toBe("CALCULATED");
    const residualInputs = residual.underlying_assumptions;
    expectRelative(residualInputs.total_equity_value, residualInputs.bv_0 + residualInputs.pv_future_wealth);
    expectRelative(
      residual.computed_fair_value,
      residualInputs.book_value_per_share + residualInputs.pv_future_wealth_per_share,
    );
  });

  test("WMT methodology history contains only comparable annual durations", async ({ request }) => {
    const response = await request.get("/api/v1/valuation/methodology?ticker=WMT", { timeout: 180_000 });
    expect(response.ok()).toBeTruthy();
    const payload = await response.json();
    const histories = [
      payload.adaptive_valuation_data?.revenue_history ?? [],
      payload.adaptive_valuation_data?.operating_income_history ?? [],
    ];
    for (const history of histories) {
      for (const row of history) {
        const durationDays = (Date.parse(row.end) - Date.parse(row.start)) / 86_400_000;
        expect(durationDays).toBeGreaterThanOrEqual(300);
        expect(durationDays).toBeLessThanOrEqual(430);
      }
    }
  });
});
