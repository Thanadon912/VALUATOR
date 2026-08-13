import http from "node:http";

const port = Number(process.env.PORT || 8000);
const snapshotTimestamp = "2026-07-18T20:00:00Z";

const companyByTicker = {
  TSLA: "Tesla, Inc.",
  JPM: "JPMorgan Chase & Co.",
  KO: "The Coca-Cola Company",
};

// Deterministic Supabase Auth + user-owned table state. Every saved-stock
// operation resolves ownership from the bearer token to exercise RLS-like
// isolation without contacting a hosted service in PR CI.
let mockUsers = []; // { id, email, password, provider }
let mockTokens = {}; // token -> user_id
let mockAuthorizationCodes = {}; // code -> user_id
let mockVerificationTokens = {}; // token_hash -> { user_id, type }
let mockWelcomeDeliveries = new Set(); // user_id
let mockSavedStocks = new Map(); // user_id -> Map<ticker, row>
let mockValuationAssumptions = new Map(); // user_id -> Map<ticker, row>
const savedStockFailuresByEmail = new Map();
const valuationAssumptionFailuresByEmail = new Map();

const b64 = (str) => Buffer.from(str).toString("base64url");

function issueSession(user) {
  const header = b64(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64(JSON.stringify({
    sub: user.id,
    email: user.email,
    role: "authenticated",
    aal: "aal1",
    exp: Math.floor(Date.now() / 1000) + 3600,
  }));
  const token = `${header}.${payload}.mocksignature`;
  mockTokens[token] = user.id;
  return {
    access_token: token,
    token_type: "bearer",
    expires_in: 3600,
    refresh_token: token,
    user: authUser(user),
  };
}

function authUser(user) {
  return {
    id: user.id,
    email: user.email,
    app_metadata: { provider: user.provider || "email", providers: [user.provider || "email"] },
    user_metadata: {},
    aud: "authenticated",
    role: "authenticated",
    confirmed_at: user.confirmed ? snapshotTimestamp : null,
    email_confirmed_at: user.confirmed ? snapshotTimestamp : null,
  };
}

function authenticatedUser(req) {
  const token = String(req.headers.authorization || "").replace("Bearer ", "");
  const userId = mockTokens[token];
  return mockUsers.find((user) => user.id === userId) || null;
}

function quote(ticker, price) {
  const hasPrice = price != null;
  return {
    ticker,
    status: hasPrice ? "success" : "unavailable",
    as_of: snapshotTimestamp,
    data: hasPrice ? {
      symbol: ticker,
      price,
      previous_close: hasPrice ? (price || 0) - 2 : null,
      change: hasPrice ? 2 : null,
      change_percent: hasPrice ? 0.8 : null,
      currency: hasPrice ? "USD" : null,
      exchange: hasPrice ? "NASDAQ" : null,
      latest_trading_day: "2026-07-18",
      market_state: "CLOSED",
      extended_price: null,
      extended_change: null,
      extended_change_percent: null,
      extended_hours_timestamp: null,
    } : null,
    sources: hasPrice
      ? [{ provider: "recorded_provider_snapshot", source_url: null, source_timestamp: snapshotTimestamp, fetched_at: snapshotTimestamp, is_stale: true }]
      : [],
    warnings: hasPrice ? ["Deterministic E2E snapshot; never served by production."] : ["No recorded snapshot for this ticker."],
  };
}

function summary(ticker) {
  const available = Boolean(companyByTicker[ticker]);
  return {
    ticker,
    status: available ? "partial" : "unavailable",
    as_of: snapshotTimestamp,
    data: {
      company_overview: {
        status: available ? "success" : "unavailable",
        message: available ? "Recorded E2E snapshot" : "No recorded snapshot",
        data: available ? { company_name: companyByTicker[ticker], logo_url: null, fmp_logo_url: null } : null,
        source_refs: available ? [0] : [],
      },
    },
    sources: available
      ? [{ provider: "recorded_provider_snapshot", source_url: null, source_timestamp: snapshotTimestamp, fetched_at: snapshotTimestamp, is_stale: true }]
      : [],
    warnings: ["Deterministic E2E snapshot; never served by production."],
  };
}

function telemetry() {
  const riskFreeRate = 0.042;
  const beta = 1;
  const marketRiskPremium = 0.055;
  return {
    market_cap: 750_000_000_000,
    market_cap_source: "recorded_provider_snapshot",
    beta,
    beta_source: "recorded_provider_snapshot",
    risk_free_rate: riskFreeRate,
    risk_free_rate_source: "U.S. Treasury recorded snapshot",
    risk_free_rate_as_of: "2026-07-18",
    market_risk_premium: marketRiskPremium,
    cost_of_equity: riskFreeRate + beta * marketRiskPremium,
    cost_of_equity_basis: "risk_free_rate + beta * market_risk_premium",
  };
}

function marginOfSafety(fairValue, price) {
  return ((fairValue - price) / price) * 100;
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

function discountedCashFlow({ projections, discountRate, perpetualGrowthRate, debt, cash, shares, regulatory }) {
  const cashFlows = projections.map((row) => regulatory
    ? row.free_cash_flow_to_equity
    : row.unlevered_free_cash_flow);
  const presentValueCashFlows = cashFlows.reduce(
    (sum, cashFlow, index) => sum + cashFlow / Math.pow(1 + discountRate, index + 1),
    0,
  );
  const terminalValue = cashFlows.at(-1) * (1 + perpetualGrowthRate)
    / (discountRate - perpetualGrowthRate);
  const presentValueTerminalValue = terminalValue
    / Math.pow(1 + discountRate, projections.length);
  const enterpriseValue = presentValueCashFlows + presentValueTerminalValue;
  const equityValue = regulatory ? enterpriseValue : enterpriseValue - debt + cash;
  return {
    terminalValue,
    presentValueCashFlows,
    presentValueTerminalValue,
    enterpriseValue,
    equityValue,
    fairValue: equityValue / shares,
  };
}

function residualIncomeFixture({ bookValue, netIncome, shares, costOfEquity, payoutRatio, persistenceFactor }) {
  const roe = netIncome / bookValue;
  let openingBookValue = bookValue;
  const residualIncomes = [];
  for (let year = 0; year < 5; year += 1) {
    const forecastNetIncome = openingBookValue * roe;
    residualIncomes.push(forecastNetIncome - openingBookValue * costOfEquity);
    openingBookValue += forecastNetIncome * (1 - payoutRatio);
  }
  const terminalValue = residualIncomes.at(-1) * persistenceFactor
    / (1 + costOfEquity - persistenceFactor);
  const presentValueResidualIncome = residualIncomes.reduce(
    (sum, income, index) => sum + income / Math.pow(1 + costOfEquity, index + 1),
    0,
  );
  const presentValueTerminalValue = terminalValue / Math.pow(1 + costOfEquity, 5);
  const futureWealth = presentValueResidualIncome + presentValueTerminalValue;
  const totalEquityValue = bookValue + futureWealth;
  return {
    roe,
    residualIncomes,
    terminalValue,
    totalEquityValue,
    futureWealth,
    bookValuePerShare: bookValue / shares,
    futureWealthPerShare: futureWealth / shares,
    fairValue: totalEquityValue / shares,
  };
}

function standardProjection(year, scenario = "base", growthRate = 0.1) {
  const scenarioGrowth = growthRate + (scenario === "bear" ? -0.05 : scenario === "bull" ? 0.05 : 0);
  const adjustment = scenario === "bear" ? 0.9 : scenario === "bull" ? 1.1 : 1;
  const revenue = 100_000_000_000 * Math.pow(1 + scenarioGrowth, year) * adjustment;
  const margin = (0.16 + year * 0.005) * adjustment;
  const nopat = revenue * margin * 0.79;
  const reinvestment = revenue * 0.035;
  return {
    year,
    revenue,
    revenue_growth: scenarioGrowth,
    ebit_margin: margin,
    ebit: revenue * margin,
    tax_rate: 0.21,
    nopat,
    sales_to_capital_ratio: 2.5,
    capital_deduction_label: "Reinvestment",
    capital_deduction_value: reinvestment,
    unlevered_free_cash_flow: nopat - reinvestment,
    free_cash_flow_to_equity: null,
  };
}

function regulatoryProjection(year, scenario = "base", growthRate = 0.05) {
  const adjustment = scenario === "bear" ? 0.92 : scenario === "bull" ? 1.08 : 1;
  const scenarioGrowth = growthRate + (scenario === "bear" ? -0.05 : scenario === "bull" ? 0.05 : 0);
  const netIncome = 48_000_000_000 * Math.pow(1 + scenarioGrowth, year) * adjustment;
  const capital = netIncome * 0.08;
  return {
    year,
    revenue: null,
    revenue_growth: null,
    net_income: netIncome,
    net_income_growth: scenarioGrowth,
    ebit_margin: null,
    ebit: null,
    tax_rate: 0.22,
    nopat: null,
    sales_to_capital_ratio: null,
    capital_deduction_label: "Required Regulatory Capital",
    capital_deduction_value: capital,
    unlevered_free_cash_flow: null,
    free_cash_flow_to_equity: netIncome - capital,
  };
}

function monteCarloFixture(fairValue, livePrice) {
  const binCount = 40;
  const lower = fairValue * 0.5;
  const width = fairValue / binCount;
  const weights = Array.from({ length: binCount }, (_, index) => {
    const z = (index - (binCount - 1) / 2) / 7;
    return Math.exp(-0.5 * z * z);
  });
  const weightTotal = weights.reduce((sum, value) => sum + value, 0);
  let assigned = 0;
  const histogram_bins = weights.map((weight, index) => {
    const count = index === binCount - 1
      ? 10_000 - assigned
      : Math.round((weight / weightTotal) * 10_000);
    assigned += count;
    return {
      lower_bound: lower + index * width,
      upper_bound: lower + (index + 1) * width,
      count,
      probability: count / 10_000,
    };
  });
  return {
    bear_p10: fairValue * 0.72,
    base_p50: fairValue,
    bull_p90: fairValue * 1.38,
    iteration_count: 10_000,
    valid_sample_count: 10_000,
    distribution: "normal",
    random_seed: 42,
    histogram_bins,
    live_price_percentile: Math.max(0, Math.min(100, (livePrice / (fairValue * 1.5)) * 100)),
  };
}

function sensitivityFixture(fairValue, growthRate, discountRate) {
  return [-0.02, -0.01, 0, 0.01, 0.02].map((growthOffset) => ({
    growth_rate: growthRate + growthOffset,
    cells: [-0.01, -0.005, 0, 0.005, 0.01].map((discountOffset) => ({
      discount_rate: discountRate + discountOffset,
      fair_value: fairValue * (1 + growthOffset * 3) * (discountRate / (discountRate + discountOffset)),
    })),
  }));
}

function dcf(ticker, searchParams = new URLSearchParams()) {
  const regulatory = ticker === "JPM";
  const price = regulatory ? 220 : ticker === "KO" ? 60 : 250;
  const baseGrowthRate = regulatory ? 0.05 : 0.1;
  const totalDebt = regulatory ? 0 : 70_000_000_000;
  const cash = regulatory ? 0 : 20_000_000_000;
  const shares = regulatory ? 3_000_000_000 : 2_640_845_070;
  const marketCap = telemetry().market_cap;
  const baseDiscountRate = regulatory
    ? telemetry().cost_of_equity
    : (marketCap / (marketCap + totalDebt)) * telemetry().cost_of_equity
      + (totalDebt / (marketCap + totalDebt)) * 0.05 * (1 - 0.21);
  const queryNumber = (name, fallback) => {
    const value = Number(searchParams.get(name));
    return Number.isFinite(value) && searchParams.has(name) ? value : fallback;
  };
  const growthRate = queryNumber("stage_1_growth_rate", baseGrowthRate);
  const perpetualGrowthRate = queryNumber("perpetual_growth_rate", 0.025);
  const discountRate = queryNumber("discount_rate", baseDiscountRate);
  const impliedTargetPrice = queryNumber("implied_target_price", price);
  const projection = regulatory ? regulatoryProjection : standardProjection;
  const projections = Array.from({ length: 7 }, (_, index) => projection(index + 1, "base", growthRate));
  const valuation = discountedCashFlow({
    projections,
    discountRate,
    perpetualGrowthRate,
    debt: totalDebt,
    cash,
    shares,
    regulatory,
  });
  const fairValue = valuation.fairValue;
  const scenarios = Object.fromEntries(
    ["bear", "base", "bull"].map((scenario) => [
      scenario,
      { projections: Array.from({ length: 7 }, (_, index) => projection(index + 1, scenario, growthRate)), harvest_start_year: null },
    ]),
  );
  const impliedGrowth = (regulatory ? 0.06 : 0.12) * (impliedTargetPrice / price);
  const impliedMargin = regulatory ? 0.24 : 0.19;
  const finalProjection = projections.at(-1) ?? {};

  return {
    ticker,
    timestamp: snapshotTimestamp,
    current_price: price,
    computed_fair_value: fairValue,
    valuation_status: "CALCULATED",
    margin_of_safety_percentage: marginOfSafety(fairValue, price),
    valuation_methodology: regulatory ? "Regulatory FCFE" : "Capitalized R&D DCF",
    engine_metadata: regulatory
      ? { tier_1_capital_ratio_used: 0.13, projected_loan_growth: 0.05, discount_rate_type: "Cost of Equity (Ke)", projection_years: 7 }
      : { capitalized_rnd_asset: 18_000_000_000, capitalized_rnd_adjustment: 2_000_000_000, adjusted_ebit_margin: 0.18, assumed_amortization_years: 5, projection_years: 7 },
    projections,
    monte_carlo_results: monteCarloFixture(fairValue, price),
    implied_expectations: {
      solver_status: "converged",
      implied_revenue_cagr: impliedGrowth,
      implied_stage_1_revenue_cagr: impliedGrowth,
      implied_operating_margin: impliedMargin,
      implied_target_ebit_margin: impliedMargin,
      implied_terminal_revenue_growth: regulatory ? null : perpetualGrowthRate,
      implied_terminal_ebit_margin: regulatory ? null : 0.18,
      implied_year_n_revenue: finalProjection.revenue ?? null,
      implied_year_n_ebit_margin: finalProjection.ebit_margin ?? null,
      implied_year_n_fcff: finalProjection.unlevered_free_cash_flow ?? finalProjection.free_cash_flow_to_equity ?? null,
      implied_projection_horizon_years: projections.length,
      target_price: impliedTargetPrice,
      feasible_curve: [
        {
          growth: impliedGrowth,
          margin: impliedMargin,
          model_value: impliedTargetPrice,
          gap: 0,
          distance: 0,
        },
        {
          growth: (regulatory ? 0.048 : 0.096) * (impliedTargetPrice / price),
          margin: regulatory ? 0.29 : 0.24,
          model_value: impliedTargetPrice,
          gap: 0,
          distance: 0.07,
        },
      ],
    },
    underlying_assumptions: {
      calculation_basis: "recorded_provider_snapshot",
      fcf_0: regulatory ? projections[0].free_cash_flow_to_equity : projections[0].unlevered_free_cash_flow,
      projections,
      terminal_value: valuation.terminalValue,
      present_value_fcfs: valuation.presentValueCashFlows,
      present_value_terminal_value: valuation.presentValueTerminalValue,
      enterprise_value: valuation.enterpriseValue,
      equity_value: valuation.equityValue,
      computed_fair_value: fairValue,
      total_debt: totalDebt,
      cash,
      shares_outstanding: shares,
      wacc: regulatory ? null : discountRate,
      discount_rate: discountRate,
      cost_of_equity: telemetry().cost_of_equity,
      discount_rate_basis: regulatory ? "cost_of_equity_only" : "true_wacc",
      wacc_basis: regulatory ? null : "true_wacc",
      wacc_used: !regulatory,
      stage_1_growth_rate: growthRate,
      perpetual_growth_rate: perpetualGrowthRate,
      projection_years: 7,
      market_cap: telemetry().market_cap,
      telemetry: telemetry(),
      wacc_components: regulatory
        ? null
        : {
            market_cap: telemetry().market_cap,
            total_debt: totalDebt,
            invested_capital: marketCap + totalDebt,
            weight_equity: marketCap / (marketCap + totalDebt),
            weight_debt: totalDebt / (marketCap + totalDebt),
            risk_free_rate: 0.042,
            beta: telemetry().beta,
            market_risk_premium: 0.055,
            cost_of_equity: telemetry().cost_of_equity,
            interest_expense: 3_500_000_000,
            cost_of_debt: 0.05,
            effective_tax_rate: 0.21,
            cost_of_debt_after_tax: 0.0395,
            wacc: discountRate,
          },
      computational_warnings: [],
    },
    forward_dcf: {
      valuation_status: "CALCULATED",
      fair_value: fairValue,
      fcf_growth_rate: regulatory ? 0.05 : 0.1,
      wacc: regulatory ? null : discountRate * 100,
      projections,
      sensitivity_matrix: sensitivityFixture(fairValue, growthRate, discountRate),
      scenarios,
    },
    reverse_dcf_sotp: { is_active: false, target_price: price, implied_growth_rate: null, segments: [] },
  };
}

function engineResponse(ticker, engine, searchParams = new URLSearchParams()) {
  const price = ticker === "JPM" ? 220 : ticker === "KO" ? 60 : 250;
  const common = {
    ticker,
    timestamp: snapshotTimestamp,
    current_price: price,
    valuation_status: "CALCULATED",
    valuation_methodology: engine,
    engine_metadata: {},
    projections: [],
    monte_carlo_results: {},
    implied_expectations: {},
  };

  if (engine === "asset-based") {
    const totalAssets = 125_000_000_000;
    const totalLiabilities = 52_000_000_000;
    const goodwill = 4_000_000_000;
    const intangibleAssets = 1_500_000_000;
    const shares = 2_640_845_070;
    const nav = totalAssets - totalLiabilities;
    const tangibleNav = nav - goodwill - intangibleAssets;
    const standardNavPerShare = nav / shares;
    const tangibleNavPerShare = tangibleNav / shares;
    return {
      ...common,
      computed_fair_value: tangibleNavPerShare,
      margin_of_safety_percentage: marginOfSafety(tangibleNavPerShare, price),
      underlying_assumptions: {
        total_assets: totalAssets,
        total_liabilities: totalLiabilities,
        goodwill,
        intangible_assets: intangibleAssets,
        nav,
        tangible_nav: tangibleNav,
        standard_nav_per_share: standardNavPerShare,
        tangible_net_net_per_share: tangibleNavPerShare,
        shares_outstanding: shares,
        computed_fair_value: tangibleNavPerShare,
        scenario_margin_of_safety_percentage: {
          standard_nav: marginOfSafety(standardNavPerShare, price),
          tangible_nav: marginOfSafety(tangibleNavPerShare, price),
        },
        scenario_margin_of_safety_basis: "(selected_backend_nav_per_share - sourced_current_price) / sourced_current_price * 100",
        telemetry: telemetry(),
      },
    };
  }

  if (engine === "ddm") {
    if (ticker === "KO") {
      const dividendsPaid = 8_000_000_000;
      const shares = 4_000_000_000;
      const historicalDividends = [6_800_000_000, 7_200_000_000, 7_600_000_000, dividendsPaid];
      const annualDividendPerShare = dividendsPaid / shares;
      const growth = Math.pow(dividendsPaid / historicalDividends[0], 1 / (historicalDividends.length - 1)) - 1;
      const costOfEquity = 0.09;
      const fairValue = annualDividendPerShare * (1 + growth) / (costOfEquity - growth);
      return {
        ...common,
        computed_fair_value: fairValue,
        valuation_status: "CALCULATED",
        margin_of_safety_percentage: marginOfSafety(fairValue, price),
        underlying_assumptions: {
          status: "APPLICABLE",
          annual_dividend_per_share: annualDividendPerShare,
          dividend_growth_cagr: growth,
          cost_of_equity: costOfEquity,
          payout_ratio: 65,
          computed_fair_value: fairValue,
          is_ddm_applicable: true,
          dividend_yield: annualDividendPerShare / price,
          applicability_reasons: [],
          telemetry: telemetry(),
        },
      };
    }
    return {
      ...common,
      computed_fair_value: null,
      valuation_status: "INAPPLICABLE",
      margin_of_safety_percentage: 0,
      underlying_assumptions: {
        status: "DDM_INAPPLICABLE",
        annual_dividend_per_share: 0,
        dividend_growth_cagr: 0,
        cost_of_equity: 0.098,
        payout_ratio: 0,
        computed_fair_value: null,
        is_ddm_applicable: false,
        dividend_yield: 0,
        applicability_reasons: [
          "No sourced dividend distribution is available.",
          "Dividend yield is below 1%.",
        ],
        telemetry: telemetry(),
      },
    };
  }

  if (engine === "relative") {
    const availablePeers = [
      { symbol: "F", name: "Ford", pe: 12.4, pb: 1.3, ev_ebitda: 8.1, overlap_score: 0.82, reason: "Recorded automotive peer", isTarget: false },
      { symbol: "GM", name: "General Motors", pe: 10.8, pb: 1.1, ev_ebitda: 7.4, overlap_score: 0.79, reason: "Recorded automotive peer", isTarget: false },
      { symbol: "TM", name: "Toyota", pe: 14.2, pb: 1.2, ev_ebitda: 9.2, overlap_score: 0.75, reason: "Recorded automotive peer", isTarget: false },
    ];
    const requestedPeers = searchParams.getAll("included_peer");
    const includedPeerSymbols = requestedPeers.length
      ? requestedPeers.filter((symbol) => availablePeers.some((peer) => peer.symbol === symbol))
      : availablePeers.map((peer) => peer.symbol);
    const peers = availablePeers.filter((peer) => includedPeerSymbols.includes(peer.symbol));
    const avgPe = median(peers.map((peer) => peer.pe));
    const avgPb = median(peers.map((peer) => peer.pb));
    const avgEvEbitda = median(peers.map((peer) => peer.ev_ebitda));
    const targetEps = 9.5;
    const targetBvps = 84;
    const targetEbitda = 24_000_000_000;
    const targetDebt = 70_000_000_000;
    const targetCash = 20_000_000_000;
    const shares = 2_640_845_070;
    const fairValues = {
      pe: avgPe * targetEps,
      pb: avgPb * targetBvps,
      evEbitda: (avgEvEbitda * targetEbitda - targetDebt + targetCash) / shares,
    };
    const fairValue = (fairValues.pe + fairValues.pb + fairValues.evEbitda) / 3;
    return {
      ...common,
      computed_fair_value: fairValue,
      margin_of_safety_percentage: marginOfSafety(fairValue, price),
      underlying_assumptions: {
        avg_pe: avgPe,
        avg_pb: avgPb,
        avg_ev_ebitda: avgEvEbitda,
        fv_pe: fairValues.pe,
        fv_pb: fairValues.pb,
        fv_ev_ebitda: fairValues.evEbitda,
        target_eps: targetEps,
        target_bvps: targetBvps,
        target_ebitda: targetEbitda,
        target_debt: targetDebt,
        target_cash: targetCash,
        shares_outstanding: shares,
        peers,
        available_peers: availablePeers,
        included_peer_symbols: includedPeerSymbols,
        peer_selection_basis: requestedPeers.length ? "user_selected_available_peers" : "all_available_peers",
        telemetry: telemetry(),
      },
    };
  }

  const residual = residualIncomeFixture({
    bookValue: 290_000_000_000,
    netIncome: 69_600_000_000,
    shares: 2_640_845_070,
    costOfEquity: telemetry().cost_of_equity,
    payoutRatio: 0.30,
    persistenceFactor: 0.50,
  });
  return {
    ...common,
    computed_fair_value: residual.fairValue,
    margin_of_safety_percentage: marginOfSafety(residual.fairValue, price),
    underlying_assumptions: {
      roe: residual.roe,
      residual_incomes: residual.residualIncomes,
      terminal_value: residual.terminalValue,
      total_equity_value: residual.totalEquityValue,
      bv_0: 290_000_000_000,
      net_income: 69_600_000_000,
      shares_outstanding: 2_640_845_070,
      cost_of_equity: telemetry().cost_of_equity,
      dividend_payout_ratio: 0.30,
      persistence_factor: 0.50,
      pv_future_wealth: residual.futureWealth,
      book_value_per_share: residual.bookValuePerShare,
      pv_future_wealth_per_share: residual.futureWealthPerShare,
      book_value_component_percentage: 290_000_000_000 / residual.totalEquityValue * 100,
      future_wealth_component_percentage: residual.futureWealth / residual.totalEquityValue * 100,
      composition_available: true,
      computed_fair_value: residual.fairValue,
      telemetry: telemetry(),
    },
  };
}

function missingResponse(ticker, engine) {
  return {
    ticker,
    timestamp: snapshotTimestamp,
    current_price: null,
    computed_fair_value: null,
    valuation_status: "MISSING_INPUT",
    margin_of_safety_percentage: 0,
    valuation_methodology: engine,
    engine_metadata: {},
    projections: [],
    monte_carlo_results: {},
    implied_expectations: {},
    underlying_assumptions: {
      calculation_basis: "missing required sourced inputs",
      missing_inputs: ["current_price", "shares_outstanding", "cash_flow_from_operations"],
      computational_warnings: ["Implied expectations unavailable: market price is missing."],
    },
  };
}

function route(pathname, searchParams) {
  console.log(`[route-sync] ${pathname}`);
  if (pathname === "/health") return { status: 200, body: { status: "ok", fixture: true } };

  if (pathname === "/api/stocks/snapshots") {
    const requested = (searchParams.get("tickers") || "").split(",").filter(Boolean);
    const data = [...new Set(requested.map((ticker) => ticker.toUpperCase()))].map((ticker) => {
      const price = ticker === "JPM" ? 220 : ticker === "TSLA" ? 250 : ticker === "KO" ? 60 : null;
      const available = price != null;
      return {
        ticker,
        company_name: companyByTicker[ticker] || null,
        price,
        change: available ? 2 : null,
        change_percent: available ? 0.8 : null,
        currency: available ? "USD" : null,
        status: available ? "success" : "unavailable",
        as_of: available ? snapshotTimestamp : null,
        sources: available
          ? [{ provider: "recorded_provider_snapshot", source_url: null, source_timestamp: snapshotTimestamp, fetched_at: snapshotTimestamp, is_stale: true }]
          : [],
        warnings: available ? ["Deterministic E2E snapshot; never served by production."] : ["No recorded snapshot for this ticker."],
      };
    });
    const statuses = new Set(data.map((item) => item.status));
    return {
      status: 200,
      body: {
        status: statuses.size === 1 ? data[0]?.status || "unavailable" : "partial",
        as_of: snapshotTimestamp,
        data,
        warnings: [],
      },
    };
  }

  const quoteMatch = pathname.match(/^\/api\/stocks\/([^/]+)\/quote$/);
  if (quoteMatch) {
    const ticker = quoteMatch[1].toUpperCase();
    let price = ticker === "JPM" ? 220 : ticker === "TSLA" ? 250 : ticker === "KO" ? 60 : null;
    if (ticker === "ZERO") price = 0;
    return { status: 200, body: quote(ticker, price) };
  }

  const summaryMatch = pathname.match(/^\/api\/stocks\/([^/]+)\/summary$/);
  if (summaryMatch) {
    const ticker = summaryMatch[1].toUpperCase();
    if (ticker === "MISSING") {
      const resp = summary("TSLA");
      resp.ticker = "MISSING";
      delete resp.data.quote;
      delete resp.data.price_history;
      delete resp.data.key_facts;
      return { status: 200, body: resp };
    }
    if (ticker === "ZERO") {
      const resp = summary("TSLA");
      resp.ticker = "ZERO";
      
      const q = quote("ZERO", 0);
      resp.data.quote = {
        status: q.status,
        message: q.warnings.join(" "),
        data: q.data,
        source_refs: [0] // mock source ref
      };
      // also mock price history to avoid layout shift issues or other crashes if it matters
      return { status: 200, body: resp };
    }
    return { status: 200, body: summary(ticker) };
  }

  const valuationMatch = pathname.match(/^\/api\/v1\/valuation\/(asset-based|dcf|ddm|relative|residual-income)$/);
  if (valuationMatch) {
    const ticker = (searchParams.get("ticker") || "").toUpperCase();
    const engine = valuationMatch[1];
    if (!companyByTicker[ticker]) return { status: 200, body: missingResponse(ticker || "UNKNOWN", engine) };
    if (engine === "dcf") return { status: 200, body: dcf(ticker, searchParams) };
    return { status: 200, body: engineResponse(ticker, engine, searchParams) };
  }

  return { status: 404, body: { detail: "Fixture route not found" } };
}

async function routeAsync(req, pathname, searchParams) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const bodyText = Buffer.concat(chunks).toString();
  let body = {};
  if (bodyText) {
    try { body = JSON.parse(bodyText); } catch {}
  }

  console.log(`[fixture-async] ${req.method} ${pathname}`);

  if (pathname === "/__test__/saved-stocks-fail-next" && req.method === "POST") {
    const email = String(body.email || "").toLowerCase();
    const failures = {
      reads: Math.max(0, Number(body.reads) || 0),
      merges: Math.max(0, Number(body.merges) || 0),
    };
    savedStockFailuresByEmail.set(email, failures);
    return { status: 200, body: failures };
  }

  if (pathname === "/__test__/valuation-assumptions-fail-next" && req.method === "POST") {
    const email = String(body.email || "").toLowerCase();
    const failures = { reads: Math.max(0, Number(body.reads) || 0) };
    valuationAssumptionFailuresByEmail.set(email, failures);
    return { status: 200, body: failures };
  }

  if (pathname === "/__test__/auth-email-state" && req.method === "POST") {
    const user = mockUsers.find((candidate) => candidate.email === String(body.email || "").toLowerCase());
    return {
      status: 200,
      body: {
        confirmed: Boolean(user?.confirmed),
        welcome_deliveries: user && mockWelcomeDeliveries.has(user.id) ? 1 : 0,
      },
    };
  }

  if (pathname === "/api/internal/auth/email/signup" && req.method === "POST") {
    if (req.headers.authorization !== "Bearer ci-deterministic-email-token-not-a-secret") {
      return { status: 401, body: { detail: { code: "internal_auth_required" } } };
    }
    const email = String(body.email || "").toLowerCase();
    if (email.includes("rate-limit")) {
      return { status: 429, body: { detail: { code: "rate_limited" } } };
    }
    let user = mockUsers.find((candidate) => candidate.email === email);
    if (!user) {
      user = {
        id: `mock-id-${Date.now()}-${mockUsers.length}`,
        email,
        password: body.password,
        provider: "email",
        confirmed: false,
      };
      mockUsers.push(user);
    }
    if (!user.confirmed) {
      mockVerificationTokens[`signup:${email}`] = { user_id: user.id, type: "signup" };
    }
    return { status: 202, body: { status: "accepted" } };
  }

  if (pathname === "/api/internal/auth/email/recovery" && req.method === "POST") {
    if (req.headers.authorization !== "Bearer ci-deterministic-email-token-not-a-secret") {
      return { status: 401, body: { detail: { code: "internal_auth_required" } } };
    }
    const email = String(body.email || "").toLowerCase();
    if (email.includes("rate-limit")) {
      return { status: 429, body: { detail: { code: "rate_limited" } } };
    }
    const user = mockUsers.find((candidate) => candidate.email === email);
    if (user) {
      mockVerificationTokens[`recovery:${email}`] = { user_id: user.id, type: "recovery" };
    }
    return { status: 202, body: { status: "accepted" } };
  }

  if (pathname === "/api/internal/auth/email/welcome" && req.method === "POST") {
    if (req.headers.authorization !== "Bearer ci-deterministic-email-token-not-a-secret") {
      return { status: 401, body: { detail: { code: "internal_auth_required" } } };
    }
    const user = mockUsers.find((candidate) => candidate.id === body.user_id);
    if (user?.confirmed) mockWelcomeDeliveries.add(user.id);
    return { status: 202, body: { status: "accepted" } };
  }

  if (pathname === "/auth/v1/signup") {
    const { email, password } = body;
    const existing = mockUsers.find((user) => user.email === email);
    if (existing) {
      return {
        status: 200,
        body: { user: { ...authUser(existing), identities: [] }, session: null },
      };
    }
    const id = "mock-id-" + Date.now();
    const user = { id, email, password, provider: "email", confirmed: true };
    mockUsers.push(user);

    if (String(email).includes("pending-confirmation")) {
      return { status: 200, body: { user: authUser(user), session: null } };
    }

    return {
      status: 200,
      body: issueSession(user),
    };
  }

  if (pathname === "/auth/v1/token" && searchParams.get("grant_type") === "password") {
    const { email, password } = body;
    const user = mockUsers.find((candidate) => candidate.email === email && candidate.password === password);
    if (!user || !user.confirmed) {
      return { status: 400, body: { error: "invalid_grant", error_description: "Invalid login credentials" } };
    }
    return { status: 200, body: issueSession(user) };
  }

  if (pathname === "/auth/v1/token" && searchParams.get("grant_type") === "pkce") {
    const userId = mockAuthorizationCodes[body.auth_code];
    const user = mockUsers.find((candidate) => candidate.id === userId);
    if (!user) return { status: 400, body: { error: "invalid_grant", error_description: "Invalid authorization code" } };
    delete mockAuthorizationCodes[body.auth_code];
    return { status: 200, body: issueSession(user) };
  }

  if (pathname === "/auth/v1/authorize") {
    let user = mockUsers.find((candidate) => candidate.email === "google-user@example.com");
    if (!user) {
      user = { id: `mock-google-${Date.now()}`, email: "google-user@example.com", password: null, provider: "google", confirmed: true };
      mockUsers.push(user);
    }
    const code = `google-code-${Date.now()}`;
    mockAuthorizationCodes[code] = user.id;
    const redirectTo = searchParams.get("redirect_to") || "http://frontend:3000/auth/callback";
    const separator = redirectTo.includes("?") ? "&" : "?";
    return { status: 302, headers: { location: `${redirectTo}${separator}code=${encodeURIComponent(code)}` }, body: null };
  }

  if (pathname === "/auth/v1/recover") {
    if (String(body.email).includes("rate-limit")) {
      return {
        status: 429,
        body: {
          code: "over_email_send_rate_limit",
          error_code: "over_email_send_rate_limit",
          msg: "Email rate limit exceeded",
        },
      };
    }
    const user = mockUsers.find((candidate) => candidate.email === body.email);
    if (user) mockAuthorizationCodes["fixture-recovery-code"] = user.id;
    return { status: 200, body: {} };
  }

  if (pathname === "/auth/v1/verify") {
    const verification = mockVerificationTokens[String(body.token_hash || "")];
    if (!verification || verification.type !== body.type) {
      return { status: 403, body: { error: "otp_expired", error_description: "Invalid token" } };
    }
    const user = mockUsers.find((candidate) => candidate.id === verification.user_id);
    if (!user) return { status: 403, body: { error: "user_not_found" } };
    if (body.type === "signup") user.confirmed = true;
    delete mockVerificationTokens[String(body.token_hash || "")];
    return { status: 200, body: issueSession(user) };
  }
  
  if (pathname === "/auth/v1/user") {
    const user = authenticatedUser(req);
    if (!user) return { status: 401, body: { error: "unauthorized" } };
    if (req.method === "PUT") {
      if (typeof body.password === "string") user.password = body.password;
      return { status: 200, body: authUser(user) };
    }
    return { status: 200, body: authUser(user) };
  }
  
  if (pathname === "/auth/v1/logout") {
    return { status: 204, body: {} };
  }

  const user = authenticatedUser(req);
  if (pathname === "/rest/v1/rpc/merge_saved_stocks") {
    if (!user) return { status: 401, body: { message: "JWT required" } };
    const failures = savedStockFailuresByEmail.get(user.email) || { reads: 0, merges: 0 };
    if (failures.merges > 0) {
      failures.merges -= 1;
      savedStockFailuresByEmail.set(user.email, failures);
      return { status: 503, body: { message: "Injected saved-stock merge failure" } };
    }
    const rows = mockSavedStocks.get(user.id) || new Map();
    for (const item of Array.isArray(body.p_items) ? body.p_items : []) {
      const current = rows.get(item.ticker);
      const incomingIsNewer = !current || Date.parse(item.last_visited_at) > Date.parse(current.last_visited_at);
      rows.set(item.ticker, {
        user_id: user.id,
        ticker: item.ticker,
        added_at: current && Date.parse(current.added_at) < Date.parse(item.added_at) ? current.added_at : item.added_at,
        last_visited_at: incomingIsNewer ? item.last_visited_at : current.last_visited_at,
        last_section: incomingIsNewer ? item.last_section : current.last_section,
      });
    }
    mockSavedStocks.set(user.id, rows);
    return { status: 200, body: [...rows.values()] };
  }

  if (pathname === "/rest/v1/saved_stocks") {
    if (!user) return { status: 401, body: { message: "JWT required" } };
    const rows = mockSavedStocks.get(user.id) || new Map();
    const tickerFilter = String(searchParams.get("ticker") || "").replace(/^eq\./, "");
    if (req.method === "GET") {
      const failures = savedStockFailuresByEmail.get(user.email) || { reads: 0, merges: 0 };
      if (failures.reads > 0) {
        failures.reads -= 1;
        savedStockFailuresByEmail.set(user.email, failures);
        return { status: 503, body: { message: "Injected saved-stock read failure" } };
      }
      const selected = [...rows.values()]
        .filter((row) => !tickerFilter || row.ticker === tickerFilter)
        .sort((left, right) => Date.parse(right.last_visited_at) - Date.parse(left.last_visited_at));
      return { status: 200, headers: { "content-range": `0-${Math.max(0, selected.length - 1)}/${selected.length}` }, body: selected };
    }
    if (req.method === "PATCH") {
      const current = rows.get(tickerFilter);
      if (current) rows.set(tickerFilter, { ...current, ...body, user_id: user.id, ticker: tickerFilter });
      mockSavedStocks.set(user.id, rows);
      return { status: 200, body: current ? [rows.get(tickerFilter)] : [] };
    }
    if (req.method === "DELETE") {
      rows.delete(tickerFilter);
      mockSavedStocks.set(user.id, rows);
      return { status: 204, body: null };
    }
  }

  if (pathname === "/rest/v1/rpc/merge_valuation_assumptions") {
    if (!user) return { status: 401, body: { message: "JWT required" } };
    const rows = mockValuationAssumptions.get(user.id) || new Map();
    for (const item of Array.isArray(body.p_items) ? body.p_items : []) {
      const ticker = String(item.ticker || "").toUpperCase();
      const current = rows.get(ticker);
      const incomingIsNewer = !current || Date.parse(item.updated_at) >= Date.parse(current.updated_at);
      if (!incomingIsNewer) continue;
      rows.set(ticker, {
        user_id: user.id,
        ticker,
        stage_1_growth_rate: item.stage_1_growth_rate,
        perpetual_growth_rate: item.perpetual_growth_rate,
        discount_rate: item.discount_rate,
        updated_at: item.updated_at,
      });
    }
    mockValuationAssumptions.set(user.id, rows);
    return { status: 200, body: [...rows.values()] };
  }

  if (pathname === "/rest/v1/valuation_assumptions") {
    if (!user) return { status: 401, body: { message: "JWT required" } };
    const rows = mockValuationAssumptions.get(user.id) || new Map();
    const tickerFilter = String(searchParams.get("ticker") || "").replace(/^eq\./, "");
    if (req.method === "GET") {
      const failures = valuationAssumptionFailuresByEmail.get(user.email) || { reads: 0 };
      if (failures.reads > 0) {
        failures.reads -= 1;
        valuationAssumptionFailuresByEmail.set(user.email, failures);
        return { status: 503, body: { message: "Injected valuation-assumption read failure" } };
      }
      const selected = [...rows.values()]
        .filter((row) => !tickerFilter || row.ticker === tickerFilter)
        .sort((left, right) => left.ticker.localeCompare(right.ticker));
      return { status: 200, headers: { "content-range": `0-${Math.max(0, selected.length - 1)}/${selected.length}` }, body: selected };
    }
    if (req.method === "DELETE") {
      rows.delete(tickerFilter);
      mockValuationAssumptions.set(user.id, rows);
      return { status: 204, body: null };
    }
  }

  return null;
}

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
  
  let result = await routeAsync(request, url.pathname, url.searchParams);
  if (!result) {
    result = route(url.pathname, url.searchParams);
  }

  response.writeHead(result.status, {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    ...(result.headers || {}),
  });
  response.end(result.body == null ? undefined : JSON.stringify(result.body));
});

server.listen(port, "0.0.0.0", () => {
  console.log(`[e2e-fixture] listening on ${port}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
