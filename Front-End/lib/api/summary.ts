import type { SummaryModule, SummaryResponse } from "./types";

const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8200";

function unavailable(message: string): SummaryModule {
  return {
    status: "unavailable",
    message,
    data: null,
    source_refs: [],
  };
}

function unavailableRevenueMix(ticker: string, message: string): SummaryModule {
  return {
    status: "unavailable",
    message,
    data: {
      ticker,
      fiscal_year: null,
      revenue_mix: {
        business_segments: [],
        products: [],
        geography: [],
        end_markets: [],
      },
      periods: {
        business_segments: [],
        products: [],
        geography: [],
        end_markets: [],
      },
      dimension_metadata: {},
    },
    source_refs: [],
  };
}

function unavailableSupplyChain(ticker: string, message: string): SummaryModule {
  return {
    status: "unavailable",
    message,
    data: {
      ticker,
      fiscal_year: null,
      extraction: {
        method: "deterministic",
        provider: null,
        model: null,
        extractor_version: null,
        cache_source: null,
        attempted_models: [],
        model_failover_used: false,
        model_failover_reason: null,
        fallback_used: false,
        fallback_reason: null,
      },
      analyzed_filings: [],
      supply_chain_exposure: {
        suppliers: [],
        manufacturing_locations: [],
        raw_material_dependencies: [],
        customer_concentrations: [],
        risks: [],
      },
    },
    source_refs: [],
  };
}

function unavailableCustomerMix(ticker: string, message: string): SummaryModule {
  return {
    status: "unavailable",
    message,
    data: {
      ticker,
      fiscal_year: null,
      analyzed_filings: [],
      customer_mix: {
        major_customers: [],
        customer_types: [],
        channel_dependencies: [],
        end_markets: [],
        risks: [],
      },
    },
    source_refs: [],
  };
}

function fallbackSummary(ticker: string, message: string): SummaryResponse {
  return {
    ticker,
    status: "error",
    as_of: null,
    data: {
      quote: unavailable(message),
      price_history: unavailable("Price history API is unavailable."),
      key_facts: unavailable("Key facts API is unavailable."),
      company_overview: unavailable("Company profile API is unavailable."),
      revenue_mix: unavailableRevenueMix(
        ticker,
        "Revenue segment API is unavailable.",
      ),
      supply_chain: unavailableSupplyChain(
        ticker,
        "Supply-chain API is unavailable.",
      ),
      customer_mix: unavailableCustomerMix(
        ticker,
        "Customer-mix API is unavailable.",
      ),
      performance: unavailable("Performance API is unavailable."),
      eps_trend: unavailable("EPS API is unavailable."),
      revenue_earnings: unavailable("Financial trend API is unavailable."),
      valuation_measures: unavailable("Valuation API is unavailable."),
      financial_highlights: unavailable("Financial highlights API is unavailable."),
      peer_comparison: unavailable("Peer comparison API is unavailable."),
    },
    sources: [],
    warnings: [message],
  };
}

function isSummaryModule(raw: unknown): boolean {
  if (!raw || typeof raw !== "object") return false;
  const obj = raw as Record<string, unknown>;
  return (
    typeof obj.status === "string" &&
    (obj.data === null || typeof obj.data === "object")
  );
}

function normalizeModule(raw: unknown, fallbackFunc: () => SummaryModule): SummaryModule {
  if (isSummaryModule(raw)) {
    const obj = raw as Record<string, unknown>;
    return {
      status: obj.status as SummaryModule["status"],
      message: typeof obj.message === "string" ? obj.message : "",
      data: obj.data as Record<string, unknown> | null,
      source_refs: Array.isArray(obj.source_refs) ? obj.source_refs : [],
    };
  }
  return fallbackFunc();
}

function normalizeSummaryResponse(ticker: string, raw: unknown): SummaryResponse {
  if (!raw || typeof raw !== "object") {
    return fallbackSummary(ticker, "Invalid response payload format.");
  }
  
  const obj = raw as Record<string, unknown>;
  const dataObj = obj.data && typeof obj.data === "object" ? (obj.data as Record<string, unknown>) : {};

  return {
    ticker: typeof obj.ticker === "string" ? obj.ticker : ticker,
    status: typeof obj.status === "string" ? (obj.status as SummaryResponse["status"]) : "error",
    as_of: typeof obj.as_of === "string" ? obj.as_of : null,
    sources: Array.isArray(obj.sources) ? obj.sources : [],
    warnings: Array.isArray(obj.warnings) ? obj.warnings : [],
    data: {
      quote: normalizeModule(dataObj.quote, () => unavailable("Quote data unavailable.")),
      price_history: normalizeModule(dataObj.price_history, () => unavailable("Price history unavailable.")),
      key_facts: normalizeModule(dataObj.key_facts, () => unavailable("Key facts unavailable.")),
      company_overview: normalizeModule(dataObj.company_overview, () => unavailable("Company profile unavailable.")),
      revenue_mix: normalizeModule(dataObj.revenue_mix, () => unavailableRevenueMix(ticker, "Revenue segment API unavailable.")),
      supply_chain: normalizeModule(dataObj.supply_chain, () => unavailableSupplyChain(ticker, "Supply-chain API unavailable.")),
      customer_mix: normalizeModule(dataObj.customer_mix, () => unavailableCustomerMix(ticker, "Customer-mix API unavailable.")),
      performance: normalizeModule(dataObj.performance, () => unavailable("Performance API unavailable.")),
      eps_trend: normalizeModule(dataObj.eps_trend, () => unavailable("EPS API unavailable.")),
      revenue_earnings: normalizeModule(dataObj.revenue_earnings, () => unavailable("Financial trend API unavailable.")),
      valuation_measures: normalizeModule(dataObj.valuation_measures, () => unavailable("Valuation API unavailable.")),
      financial_highlights: normalizeModule(dataObj.financial_highlights, () => unavailable("Financial highlights API unavailable.")),
      peer_comparison: normalizeModule(dataObj.peer_comparison, () => unavailable("Peer comparison API unavailable.")),
    }
  };
}

export async function getSummary(ticker: string): Promise<SummaryResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/stocks/${ticker}/summary`, {
      // Bucket A structural data is cached server-side (SEC 14-day); never
      // freeze the page with an ISR layer. Live price telemetry is handled
      // client-side via the shared useLiveQuote() SWR stream.
      cache: 'no-store',
      signal: AbortSignal.timeout(60000),
    });

    if (!response.ok) {
      return fallbackSummary(ticker, `Summary API returned ${response.status}.`);
    }

    const rawData = await response.json();
    return normalizeSummaryResponse(ticker, rawData);
  } catch {
    return fallbackSummary(
      ticker,
      "Summary API is not reachable. Start the FastAPI service and retry.",
    );
  }
}
