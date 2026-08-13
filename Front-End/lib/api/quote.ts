import type { LiveQuoteResponse } from "./types";

const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8200";

/**
 * Server-side fetcher for the initial (Bucket B) quote seed.
 *
 * Used once in the workspace layout to seed the SWR fallback so the very
 * first paint is instant — no client fetch, no spinner. Subsequent live
 * refreshes are driven by the client SWR stream in LiveQuoteProvider.
 *
 * Never throws into the render path; a backend failure degrades to an
 * `unavailable` envelope so the structural page still renders.
 */
export async function getLiveQuote(
  ticker: string,
): Promise<LiveQuoteResponse> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/stocks/${ticker}/quote`,
      {
        cache: 'no-store',
        signal: AbortSignal.timeout(30000),
      },
    );

    if (!response.ok) {
      return unavailableQuote(ticker, `API returned ${response.status}.`);
    }

    return (await response.json()) as LiveQuoteResponse;
  } catch {
    return unavailableQuote(
      ticker,
      "Live quote API is not reachable. Start the FastAPI service and retry.",
    );
  }
}

function unavailableQuote(
  ticker: string,
  message: string,
): LiveQuoteResponse {
  return {
    ticker,
    status: "unavailable",
    as_of: null,
    data: {
      symbol: ticker,
      price: null,
      previous_close: null,
      change: null,
      change_percent: null,
      currency: null,
      exchange: null,
      latest_trading_day: null,
      market_state: null,
      extended_price: null,
      extended_change: null,
      extended_change_percent: null,
      extended_hours_timestamp: null,
    },
    sources: [],
    warnings: [message],
  };
}

/** Client-side fetcher goes through the Next rewrite/proxy to avoid leaking a backend port into the browser. */
export const liveQuoteFetcher = (ticker: string): Promise<LiveQuoteResponse> =>
  fetch(`/api/stocks/${ticker}/quote`, {
    cache: 'no-store',
    signal: AbortSignal.timeout(60000),
  }).then((res) => res.json() as Promise<LiveQuoteResponse>);
