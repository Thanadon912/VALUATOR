"use client";

import { ChevronLeft, ChevronRight, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { useSavedStocks } from "./saved-stocks-provider";
import type { SavedStock, SavedStockSnapshot } from "./types";
import { useStockSnapshots } from "./use-stock-snapshots";
import { savedStockHref } from "./validation";
import { StatusNotice } from "@/components/ui/status-notice";

const ACCOUNT_PAGE_SIZE = 10;
const LANDING_ITEM_COUNT = 3;
type AccountSort = "recent" | "ticker" | "move";

type RemovalFeedback =
  | { kind: "undo"; item: SavedStock }
  | { kind: "restore-error"; item: SavedStock }
  | { kind: "restored"; ticker: string };

export function SavedStocksPanel({ variant = "landing" }: { variant?: "landing" | "account" }) {
  const { items, mode, loading: storeLoading, error: storeError, remove, restore, retrySync } = useSavedStocks();
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<AccountSort>("recent");
  const [removalFeedback, setRemovalFeedback] = useState<RemovalFeedback | null>(null);
  const feedbackTimerRef = useRef<number | null>(null);
  const snapshotTickers = useMemo(
    () => (variant === "account" ? items : items.slice(0, LANDING_ITEM_COUNT)).map((item) => item.ticker),
    [items, variant],
  );
  const market = useStockSnapshots(snapshotTickers);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const managedItems = useMemo(() => {
    if (variant === "landing") return items.slice(0, LANDING_ITEM_COUNT);

    const filtered = normalizedQuery
      ? items.filter((item) => {
        const companyName = market.snapshots.get(item.ticker)?.company_name ?? "";
        return item.ticker.toLocaleLowerCase().includes(normalizedQuery)
          || companyName.toLocaleLowerCase().includes(normalizedQuery);
      })
      : [...items];

    return filtered.sort((left, right) => {
      if (sort === "ticker") return left.ticker.localeCompare(right.ticker);
      if (sort === "move") {
        const leftMove = market.snapshots.get(left.ticker)?.change_percent;
        const rightMove = market.snapshots.get(right.ticker)?.change_percent;
        if (leftMove == null && rightMove == null) return left.ticker.localeCompare(right.ticker);
        if (leftMove == null) return 1;
        if (rightMove == null) return -1;
        return rightMove - leftMove || left.ticker.localeCompare(right.ticker);
      }
      return Date.parse(right.lastVisitedAt) - Date.parse(left.lastVisitedAt)
        || left.ticker.localeCompare(right.ticker);
    });
  }, [items, market.snapshots, normalizedQuery, sort, variant]);
  const pageCount = Math.max(1, Math.ceil(managedItems.length / ACCOUNT_PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visible = useMemo(
    () => variant === "landing"
      ? managedItems
      : managedItems.slice((safePage - 1) * ACCOUNT_PAGE_SIZE, safePage * ACCOUNT_PAGE_SIZE),
    [managedItems, safePage, variant],
  );

  useEffect(() => () => {
    if (feedbackTimerRef.current !== null) window.clearTimeout(feedbackTimerRef.current);
  }, []);

  function scheduleFeedbackClear(delay: number) {
    if (feedbackTimerRef.current !== null) window.clearTimeout(feedbackTimerRef.current);
    feedbackTimerRef.current = window.setTimeout(() => {
      setRemovalFeedback(null);
      feedbackTimerRef.current = null;
    }, delay);
  }

  async function handleRemove(item: SavedStock) {
    if (!await remove(item.ticker)) return;
    setRemovalFeedback({ kind: "undo", item });
    scheduleFeedbackClear(8_000);
  }

  async function handleUndo() {
    if (removalFeedback?.kind !== "undo" && removalFeedback?.kind !== "restore-error") return;
    const item = removalFeedback.item;
    if (!await restore(item)) {
      if (feedbackTimerRef.current !== null) window.clearTimeout(feedbackTimerRef.current);
      feedbackTimerRef.current = null;
      setRemovalFeedback({ kind: "restore-error", item });
      return;
    }
    setRemovalFeedback({ kind: "restored", ticker: item.ticker });
    scheduleFeedbackClear(4_000);
  }

  return (
    <section
      aria-labelledby={`saved-stocks-${variant}-title`}
      className={variant === "landing"
        ? "saved-stocks-panel rounded-xl border border-white/12 bg-[#080B09]/88 p-4 sm:p-5"
        : "saved-stocks-panel rounded-xl border border-[#1E293B] bg-[#0B0F17]/90 p-4 sm:p-5"}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-3">
        <div>
          {variant === "landing" ? <p className="text-xs font-semibold text-[#B7FF3C]">Recent work</p> : null}
          <h2 id={`saved-stocks-${variant}-title`} className={`${variant === "landing" ? "mt-1 " : ""}text-lg font-bold text-[#EFFAF4]`}>
            Saved Stocks
          </h2>
        </div>
        <div className="flex items-center gap-3 text-xs text-[#90B09E]">
          {items.length > 0 ? (
            <span>{variant === "landing"
              ? `${visible.length} of ${items.length} shown`
              : normalizedQuery
                ? `${managedItems.length} of ${items.length} matched`
                : `${items.length} saved`}</span>
          ) : null}
          {variant === "landing" && items.length > 0 ? (
            <Link href="/account" className="min-h-11 content-center font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
              View all saved
            </Link>
          ) : null}
        </div>
      </div>

      {storeError ? (
        <StatusNotice
          className="mt-3"
          tone="error"
          title="Saved stocks couldn’t sync"
          compact
          actions={<button type="button" onClick={() => void retrySync()} className="min-h-11 font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">Retry sync</button>}
        >
          {storeError}
        </StatusNotice>
      ) : null}


      {variant === "account" && items.length > 0 ? (
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <label className="min-w-0 flex-1 text-xs font-medium text-[#90B09E]">
            Search saved stocks
            <input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="Ticker or company"
              className="mt-1 block min-h-11 w-full rounded-[10px] border border-[#2A3B31] bg-[#070A0D] px-3 text-sm text-[#EFFAF4] placeholder:text-[#9AA69E] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            />
          </label>
          <label className="text-xs font-medium text-[#90B09E] sm:w-48">
            Sort saved stocks
            <select
              value={sort}
              onChange={(event) => {
                setSort(event.target.value as AccountSort);
                setPage(1);
              }}
              className="mt-1 block min-h-11 w-full rounded-[10px] border border-[#2A3B31] bg-[#070A0D] px-3 text-sm text-[#EFFAF4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              <option value="recent">Recently opened</option>
              <option value="ticker">Ticker A–Z</option>
              <option value="move">Daily move</option>
            </select>
          </label>
        </div>
      ) : null}

      {storeLoading ? (
        <div className="mt-4 grid gap-2" aria-busy="true" aria-label="Loading saved stocks">
          {Array.from({ length: variant === "landing" ? 2 : 4 }, (_, index) => (
            <div key={index} className="h-16 animate-pulse rounded-lg bg-white/5" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="py-7 text-center">
          <Star className="mx-auto size-5 text-[#6D7F73]" aria-hidden="true" />
          <p className="mt-3 text-sm font-semibold text-[#D1D1CA]">
            {mode === "authenticated" ? "No saved stocks in your account yet." : "No saved stocks on this device yet."}
          </p>
          <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-[#8C9A90]">
            Open a company workspace and use the star control. Searching and valuation remain available without an account.
          </p>
          <Link href="/#find-fair-value" className="mt-3 inline-flex min-h-11 items-center rounded-[10px] border border-[#2A3B31] px-4 text-sm font-semibold text-[#EFFAF4] transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
            Find a company
          </Link>
        </div>
      ) : variant === "account" && managedItems.length === 0 ? (
        <div className="py-7 text-center">
          <p className="text-sm font-semibold text-[#D1D1CA]">No saved stocks match “{query.trim()}”.</p>
          <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-[#8C9A90]">Search by ticker or company name, or clear the search to see the complete list.</p>
          <button type="button" onClick={() => {
            setQuery("");
            setPage(1);
          }} className="mt-3 min-h-11 rounded-[10px] border border-[#2A3B31] px-4 text-sm font-semibold text-[#EFFAF4] hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
            Clear search
          </button>
        </div>
      ) : (
        <div
          data-testid={`saved-stocks-${variant}-list`}
          className="mt-3 divide-y divide-white/8"
        >
          {visible.map((item) => (
            <SavedStockRow
              key={item.ticker}
              item={item}
              snapshot={market.snapshots.get(item.ticker)}
              marketLoading={market.loading}
              onRemove={() => void handleRemove(item)}
            />
          ))}
        </div>
      )}

      {market.error ? <p className="mt-3 text-xs text-[#FFB4A9]" role="status">Current market data unavailable. Saved routes are still available.</p> : null}

      {removalFeedback ? (
        <StatusNotice
          className="mt-3"
          tone={removalFeedback.kind === "restore-error" ? "error" : "info"}
          title={removalFeedback.kind === "undo" ? "Saved stock removed" : removalFeedback.kind === "restore-error" ? "Saved stock wasn’t restored" : "Saved stock restored"}
          compact
          actions={removalFeedback.kind === "undo" || removalFeedback.kind === "restore-error" ? (
            <button
              type="button"
              onClick={() => void handleUndo()}
              className="min-h-11 font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              {removalFeedback.kind === "undo" ? "Undo" : "Try restore"}
            </button>
          ) : undefined}
        >
          <span>
            {removalFeedback.kind === "undo"
              ? `${removalFeedback.item.ticker} removed from saved stocks.`
              : removalFeedback.kind === "restore-error"
                ? `${removalFeedback.item.ticker} could not be restored. Your removal is unchanged.`
                : `${removalFeedback.ticker} restored to saved stocks.`}
          </span>
        </StatusNotice>
      ) : null}

      <footer className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3 text-xs text-[#8C9A90]">
        <span>{mode === "authenticated" ? "Synced to your account" : "Stored on this device"}</span>
        {mode === "guest" && variant === "landing" ? (
          <Link href="/login?next=%2Faccount" className="min-h-11 content-center font-semibold text-[#B7FF3C] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
            Sign in to sync
          </Link>
        ) : null}
      </footer>

      {variant === "account" && pageCount > 1 ? (
        <nav className="mt-4 flex items-center justify-end gap-2" aria-label="Saved stocks pages">
          <button
            type="button"
            disabled={safePage === 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-white/15 px-3 text-xs font-semibold text-[#D1D1CA] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] disabled:opacity-40"
          >
            <ChevronLeft className="size-4" aria-hidden="true" /> Previous
          </button>
          <span className="px-2 text-xs tabular-nums text-[#90B09E]">{safePage} / {pageCount}</span>
          <button
            type="button"
            disabled={safePage === pageCount}
            onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            className="inline-flex min-h-11 items-center gap-1 rounded-lg border border-white/15 px-3 text-xs font-semibold text-[#D1D1CA] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] disabled:opacity-40"
          >
            Next <ChevronRight className="size-4" aria-hidden="true" />
          </button>
        </nav>
      ) : null}
    </section>
  );
}

function SavedStockRow({
  item,
  snapshot,
  marketLoading,
  onRemove,
}: {
  item: SavedStock;
  snapshot: SavedStockSnapshot | undefined;
  marketLoading: boolean;
  onRemove: () => void;
}) {
  const price = formatPrice(snapshot?.price ?? null, snapshot?.currency ?? null);
  const change = formatChange(snapshot?.change_percent ?? null);
  const changePositive = (snapshot?.change_percent ?? 0) >= 0;
  const provenance = formatSnapshotProvenance(snapshot, marketLoading);

  return (
    <article className="grid min-w-0 grid-cols-[minmax(0,1fr)_2.75rem] gap-3 py-3 sm:items-center">
      <Link
        href={savedStockHref(item)}
        className="saved-stock-row-link group grid min-w-0 gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
      >
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <strong className="font-mono text-sm text-[#EFFAF4] group-hover:text-[#B7FF3C]">{item.ticker}</strong>
            <span className="truncate text-xs text-[#90B09E]" title={snapshot?.company_name ?? undefined}>
              {snapshot?.company_name ?? (marketLoading ? "Loading company…" : "Company name unavailable")}
            </span>
          </div>
          <p className="mt-1 truncate text-xs text-[#8C9A90]">
            Last opened: {item.lastSection} · {formatTimestamp(item.lastVisitedAt)}
          </p>
        </div>
        <div className="saved-stock-row-market min-w-0">
          <p className="font-mono text-sm font-semibold tabular-nums text-[#EFFAF4]">{marketLoading ? "Loading…" : price}</p>
          <p className={`mt-1 text-xs font-semibold tabular-nums ${snapshot?.change_percent == null ? "text-[#8C9A90]" : changePositive ? "text-[#34D399]" : "text-[#FB7185]"}`}>
            {change}
          </p>
          <p className={`mt-1 truncate text-xs ${snapshotSource(snapshot)?.is_stale ? "text-[#F5B942]" : "text-[#8C9A90]"}`} title={provenance}>
            {provenance}
          </p>
        </div>
      </Link>
      <button
        type="button"
        onClick={onRemove}
        className="inline-flex size-11 items-center justify-center self-start rounded-lg text-[#7E9185] hover:bg-[#FB7185]/10 hover:text-[#FB7185] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] sm:self-center"
        aria-label={`Remove ${item.ticker} from saved stocks`}
      >
        <Trash2 className="size-4" aria-hidden="true" />
      </button>
    </article>
  );
}

function formatPrice(value: number | null, currency: string | null): string {
  if (value == null) return "Price unavailable";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currency ?? ""} ${value.toFixed(2)}`.trim();
  }
}

function formatChange(value: number | null): string {
  if (value == null) return "Change unavailable";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatTimestamp(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(timestamp);
}

function snapshotSource(snapshot: SavedStockSnapshot | undefined) {
  return snapshot?.sources.find((source) => source.provider !== "SEC Company Tickers");
}

function formatSnapshotProvenance(
  snapshot: SavedStockSnapshot | undefined,
  marketLoading: boolean,
): string {
  if (marketLoading) return "Loading source…";
  const source = snapshotSource(snapshot);
  if (!source) return "Price source unavailable";

  const timestamp = source.source_timestamp ?? snapshot?.as_of ?? source.fetched_at;
  const freshness = source.is_stale ? "stale" : "fresh";
  return `${source.provider} · ${freshness} · ${formatTimestamp(timestamp)}`;
}
