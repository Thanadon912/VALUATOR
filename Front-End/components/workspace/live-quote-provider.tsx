"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import useSWR from "swr";

import { liveQuoteFetcher } from "@/lib/api/quote";
import type { LiveQuoteResponse } from "@/lib/api/types";

/**
 * Bucket B — Real-Time live-quote stream shared across the workspace.
 *
 * One SWR stream per ticker is mounted in the /stocks/[ticker] layout, so
 * every page (summary, statistics, financials, holders, …) shares the same
 * live price telemetry without each refetching independently.
 *
 * Hydration policy (stale-while-revalidate on tab swap):
 *   1. Instant render — the server-supplied `fallback` paints immediately so
 *      structural cards never wait for a live fetch.
 *   2. Background refresh — SWR revalidates silently against the
 *      `/api/stocks/{ticker}/quote` Bucket B endpoint on focus and every
 *      `refreshInterval` (≤ backend's 10s cap).
 *   3. Silent hydration — consumers read `useLiveQuote()`; when fresh data
 *      resolves they update price-dependent UI without a layout shift or
 *      re-triggering loaders.
 */

type LiveQuoteContextValue = {
  data: LiveQuoteResponse | undefined;
  isLoading: boolean;
  error: Error | undefined;
};

const LiveQuoteContext = createContext<LiveQuoteContextValue | null>(null);

/** Stable string cache key so the SWR `fallback` map matches exactly. */
function quoteKey(ticker: string): string {
  return `live-quote:${ticker}`;
}

export function LiveQuoteProvider({
  ticker,
  fallback,
  children,
}: {
  ticker: string;
  fallback: LiveQuoteResponse;
  children: ReactNode;
}) {
  const key = useMemo(() => quoteKey(ticker), [ticker]);
  const { data, error, isLoading } = useSWR(key, () => liveQuoteFetcher(ticker), {
    fallback: { [key]: fallback },
    // ≤ backend Bucket B cap (8s server TTL). Keep live data fresh.
    refreshInterval: 10000,
    // Free refresh whenever the user returns to the workspace tab.
    revalidateOnFocus: true,
    revalidateOnReconnect: true,
    // Dedupe rapid tab switches within the same window.
    dedupingInterval: 8000,
    // Keep previous data visible while revalidating (no flash).
    keepPreviousData: true,
  });

  return (
    <LiveQuoteContext.Provider value={{ data, error, isLoading }}>
      {children}
    </LiveQuoteContext.Provider>
  );
}

export function useLiveQuote(): LiveQuoteContextValue {
  const ctx = useContext(LiveQuoteContext);
  if (ctx === null) {
    throw new Error("useLiveQuote must be used within a LiveQuoteProvider");
  }
  return ctx;
}
