"use client";

import { useEffect, useMemo, useState } from "react";

import type { SavedStockSnapshot, SavedStockSnapshotsResponse } from "./types";

const SNAPSHOT_BATCH_SIZE = 20;

export function useStockSnapshots(tickers: string[]) {
  const key = useMemo(() => tickers.join(","), [tickers]);
  const [state, setState] = useState<{
    key: string;
    snapshots: Map<string, SavedStockSnapshot>;
    error: string | null;
  }>({ key: "", snapshots: new Map(), error: null });

  useEffect(() => {
    if (!key) return;

    const controller = new AbortController();

    const batches = chunk(key.split(","), SNAPSHOT_BATCH_SIZE);

    Promise.allSettled(batches.map(async (batch) => {
      const response = await fetch(`/api/stocks/snapshots?tickers=${encodeURIComponent(batch.join(","))}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Market snapshots returned HTTP ${response.status}.`);
      return response.json() as Promise<SavedStockSnapshotsResponse>;
    }))
      .then((results) => {
        if (controller.signal.aborted) return;
        const successful = results.flatMap((result) => result.status === "fulfilled" ? result.value.data : []);
        const failedCount = results.filter((result) => result.status === "rejected").length;
        setState({
          key,
          snapshots: new Map(successful.map((item) => [item.ticker, item])),
          error: failedCount === 0
            ? null
            : successful.length > 0
              ? "Some market snapshots are temporarily unavailable."
              : "Market snapshots are temporarily unavailable.",
        });
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          key,
          snapshots: new Map(),
          error: requestError instanceof Error ? requestError.message : "Market snapshots are unavailable.",
        });
      });

    return () => controller.abort();
  }, [key]);

  if (!key) return { snapshots: new Map<string, SavedStockSnapshot>(), loading: false, error: null };
  if (state.key !== key) return { snapshots: new Map<string, SavedStockSnapshot>(), loading: true, error: null };
  return { snapshots: state.snapshots, loading: false, error: state.error };
}

function chunk<T>(items: T[], size: number): T[][] {
  const batches: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    batches.push(items.slice(index, index + size));
  }
  return batches;
}
