import http from "node:http";

const BILLION = 1_000_000_000;
const now = "2026-06-25T00:00:00Z";
const source = {
  provider: "mock",
  source_url: null,
  source_timestamp: now,
  fetched_at: now,
  is_stale: false,
};

function metric(name, value, unit = "USD") {
  return {
    name,
    value,
    unit,
    currency: unit === "USD" ? "USD" : null,
    status: "reported",
    basis: "mock_ui_smoke",
  };
}

function ratio(name, value) {
  return {
    name,
    value,
    unit: "ratio",
    currency: null,
    status: "calculated",
    basis: "mock_ui_smoke",
  };
}

function inputResponse(ticker) {
  return {
    ticker,
    status: "success",
    as_of: now,
    data: {
      company_name: "Microsoft Corp Mock Assisted DCF",
      model_version: "mock-phase-c",
      modes: { basic: { status: "available" }, advanced: { status: "available" } },
      selected_starting_basis: {
        basis_type: "latest_ttm",
        selected_by: "system",
        period_start: "2025-04-01",
        period_end: "2026-03-31",
        calculation_method: "annual_plus_current_ytd_minus_prior_ytd",
        source_facts: [],
        data_quality: "high",
        reason_codes: [],
        warnings: [],
        user_overridden: false,
      },
      starting_basis_options: [],
      historical_metrics: {
        annual: [
          { fiscal_year: 2025, ebit_margin: ratio("ebit_margin", 0.34) },
          { fiscal_year: 2024, ebit_margin: ratio("ebit_margin", 0.32) },
          { fiscal_year: 2023, ebit_margin: ratio("ebit_margin", 0.31) },
        ],
        latest_ttm: {
          revenue: metric("revenue", 250 * BILLION),
          ebit: metric("ebit", 85 * BILLION),
          ebit_margin: ratio("ebit_margin", 0.34),
          depreciation_amortization: metric("depreciation_amortization", 18 * BILLION),
          capital_expenditure: metric("capital_expenditure", 22 * BILLION),
          change_in_net_working_capital: metric("change_in_net_working_capital", 3 * BILLION),
          fcff: metric("fcff", 78 * BILLION),
          interest_expense: metric("interest_expense", 2 * BILLION),
          stock_based_compensation: metric("stock_based_compensation", 8 * BILLION),
        },
      },
      equity_bridge_inputs: {
        cash_and_equivalents: metric("cash_and_equivalents", 80 * BILLION),
        total_debt: metric("total_debt", 50 * BILLION),
        shares_outstanding: {
          name: "shares_outstanding",
          value: 7.4 * BILLION,
          unit: "shares",
          currency: null,
          status: "reported",
          basis: "mock_ui_smoke",
        },
        period_end: "2026-03-31",
      },
      assumption_suggestions: {
        revenue_growth_rate: ratio("revenue_growth_rate", 0.07),
        tax_rate: ratio("tax_rate", 0.21),
        depreciation_amortization_percent_of_revenue: ratio("depreciation_amortization_percent_of_revenue", 0.075),
        capital_expenditure_percent_of_revenue: ratio("capital_expenditure_percent_of_revenue", 0.09),
        change_in_nwc_percent_of_revenue: ratio("change_in_nwc_percent_of_revenue", 0.015),
      },
      scenarios: {
        base: {
          name: "Base",
          status: "available",
          lifecycle_state: "available",
          can_calculate: true,
          assumptions: { revenue_growth_rate: 0.07, forecast_horizon_years: 5 },
          transformation: {},
          missing_inputs: [],
          validation_errors: [],
        },
        bear: {
          name: "Bear",
          status: "available",
          lifecycle_state: "available",
          can_calculate: false,
          can_initialize_from_base: true,
          assumptions: {},
          transformation: {},
          missing_inputs: [],
          validation_errors: [],
        },
        bull: {
          name: "Bull",
          status: "available",
          lifecycle_state: "available",
          can_calculate: false,
          can_initialize_from_base: true,
          assumptions: {},
          transformation: {},
          missing_inputs: [],
          validation_errors: [],
        },
      },
      wacc: {
        status: "missing_input",
        components: {
          pre_tax_cost_of_debt: {
            ...ratio("pre_tax_cost_of_debt", 0.045),
            source_freshness: { freshnessStatus: "fresh" },
            warnings: [],
          },
        },
        warnings: [],
      },
      sensitivity: { status: "missing_input", tables: {}, warnings: [] },
      sbc_and_dilution: {
        status: "available",
        ttm_stock_based_compensation: metric("ttm_stock_based_compensation", 8 * BILLION),
        warnings: [],
      },
      normalization_review: { status: "available", options: [], warnings: [] },
      source_lineage: [],
      validation: {
        status: "available",
        can_calculate_base: true,
        base_state: "available",
        missing_inputs: [],
        validation_errors: [],
        warnings: [],
      },
      data_quality: { label: "complete", reason_codes: [], warnings: [] },
    },
    sources: [source],
    warnings: [],
  };
}

function calculationResponse(ticker, body) {
  const assumptions = body.assumptions || {};
  const years = assumptions.forecast_years || 5;
  const discountRate = assumptions.wacc?.value || 0.085;
  const terminalGrowth = assumptions.terminal_growth_rate?.value || 0.025;
  let revenue =
    (body.base_revenue?.value || 250 * BILLION) +
    (body.normalization_adjustments?.[0]?.value || 0);
  let shares = body.equity_bridge?.diluted_shares?.value || 7.4 * BILLION;
  let explicitPv = 0;
  const projectedRows = [];

  for (let index = 0; index < years; index += 1) {
    const growth = assumptions.revenue_growth_rates?.[index]?.value ?? 0.07;
    const margin =
      assumptions.ebit_margin_by_year?.[index]?.value ?? assumptions.ebit_margin?.value ?? 0.34;
    const tax =
      assumptions.tax_rate_by_year?.[index]?.value ?? assumptions.tax_rate?.value ?? 0.21;
    const previousRevenue = revenue;
    revenue *= 1 + growth;
    const reinvestment =
      assumptions.reinvestment_method === "sales_to_capital"
        ? (revenue - previousRevenue) / (assumptions.sales_to_capital_by_year?.[index]?.value ?? 2.5)
        : revenue * 0.03;
    const sbc =
      revenue * (assumptions.stock_based_compensation_percent_of_revenue_by_year?.[index]?.value ?? 0);
    const fcff = revenue * margin * (1 - tax) - reinvestment + sbc;
    const discountFactor = 1 / (1 + discountRate) ** (index + 1);
    shares *= 1 + (assumptions.share_dilution_rate_by_year?.[index]?.value ?? 0);
    explicitPv += fcff * discountFactor;
    projectedRows.push({
      year: index + 1,
      revenue,
      fcff,
      free_cash_flow: fcff,
      discount_factor: discountFactor,
      present_value: fcff * discountFactor,
      reinvestment,
      stock_based_compensation: sbc,
      diluted_shares: shares,
      reinvestment_method: assumptions.reinvestment_method || "direct_fcff_drivers",
    });
  }

  const terminalYearFcff = projectedRows.at(-1).fcff;
  const terminalFcff = terminalYearFcff * (1 + terminalGrowth);
  const terminalValue = terminalFcff / (discountRate - terminalGrowth);
  const terminalPresentValue = terminalValue / (1 + discountRate) ** years;
  const enterpriseValue = explicitPv + terminalPresentValue;
  const bridge = body.equity_bridge || {};
  const cash = bridge.cash_and_equivalents?.value || 0;
  const debt = bridge.total_debt?.value || 0;
  const marketable = bridge.marketable_securities?.value || 0;
  const preferred = bridge.preferred_stock?.value || 0;
  const equityValue = enterpriseValue + cash + marketable - debt - preferred;

  return {
    ticker,
    status: "success",
    as_of: now,
    data: {
      status: "calculated",
      projected_cash_flows: projectedRows,
      terminal_value: {
        value: terminalValue,
        present_value: terminalPresentValue,
        terminal_year_fcff: terminalYearFcff,
        terminal_fcff: terminalFcff,
        terminal_growth_rate: terminalGrowth,
        wacc: discountRate,
        wacc_terminal_growth_spread: discountRate - terminalGrowth,
        discount_factor_to_present: 1 / (1 + discountRate) ** years,
      },
      enterprise_value: {
        value: enterpriseValue,
        explicit_forecast_present_value: explicitPv,
        terminal_present_value: terminalPresentValue,
        explicit_forecast_percent_of_enterprise_value: explicitPv / enterpriseValue,
        terminal_value_percent_of_enterprise_value: terminalPresentValue / enterpriseValue,
      },
      equity_value: equityValue,
      fair_value_per_share: equityValue / shares,
      equity_bridge: {
        equity_value: equityValue,
        rows: [
          { label: "Enterprise Value", operation: "equals", value: enterpriseValue },
          { label: "Cash and Equivalents", operation: "add", value: cash, source_input: bridge.cash_and_equivalents },
          { label: "Marketable Securities", operation: "add", value: marketable, source_input: bridge.marketable_securities },
          { label: "Total Debt", operation: "subtract", value: debt, source_input: bridge.total_debt },
          { label: "Preferred Stock", operation: "subtract", value: preferred, source_input: bridge.preferred_stock },
          { label: "Equity Value", operation: "equals", value: equityValue },
          { label: "Diluted Shares", operation: "divide", value: shares, source_input: bridge.diluted_shares },
        ],
      },
      warnings: ["Terminal value is more than 75% of enterprise value; review long-term assumptions."],
      calculation_basis: "mock_ui_smoke",
    },
    sources: [source],
    warnings: [],
  };
}

const port = Number(process.env.PORT || 8007);

const server = http.createServer((request, response) => {
  response.setHeader("Access-Control-Allow-Origin", "*");
  response.setHeader("Access-Control-Allow-Headers", "content-type");
  response.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  const match = request.url.match(/^\/api\/stocks\/([^/]+)\/dcf(?:\/inputs)?$/);
  if (!match) {
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "not found" }));
    return;
  }

  const ticker = decodeURIComponent(match[1]).toUpperCase();
  if (request.method === "GET" && request.url.endsWith("/inputs")) {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(inputResponse(ticker)));
    return;
  }

  if (request.method === "POST") {
    let raw = "";
    request.on("data", (chunk) => {
      raw += chunk;
    });
    request.on("end", () => {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(calculationResponse(ticker, JSON.parse(raw || "{}"))));
    });
    return;
  }

  response.writeHead(405, { "content-type": "application/json" });
  response.end(JSON.stringify({ error: "method not allowed" }));
});

server.listen(port, "127.0.0.1", () => {
  console.log(`mock dcf api on ${port}`);
});
