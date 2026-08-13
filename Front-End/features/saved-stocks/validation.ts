import { normalizeTicker } from "@/lib/validation/ticker";

import type { SavedStock, SavedStockSection } from "./types";
import { SAVED_STOCK_SECTIONS } from "./types";

const SECTION_SET = new Set<string>(SAVED_STOCK_SECTIONS);

export function normalizeSavedStockSection(value: unknown): SavedStockSection | null {
  return typeof value === "string" && SECTION_SET.has(value)
    ? (value as SavedStockSection)
    : null;
}

export function sectionFromPathname(pathname: string): {
  ticker: string;
  section: SavedStockSection;
} | null {
  const match = pathname.match(/^\/stocks\/([^/]+)\/(summary|news|valuation)\/?$/i);
  if (!match) return null;

  const ticker = normalizeTicker(decodeURIComponent(match[1]));
  const section = normalizeSavedStockSection(match[2].toLowerCase());
  return ticker && section ? { ticker, section } : null;
}

export function savedStockHref(item: Pick<SavedStock, "ticker" | "lastSection">): string {
  const ticker = normalizeTicker(item.ticker);
  const section = normalizeSavedStockSection(item.lastSection);
  return ticker && section
    ? `/stocks/${encodeURIComponent(ticker)}/${section}`
    : "/";
}

export function normalizeSavedStock(value: unknown, now = new Date()): SavedStock | null {
  if (!value || typeof value !== "object") return null;

  const raw = value as Record<string, unknown>;
  const ticker = typeof raw.ticker === "string" ? normalizeTicker(raw.ticker) : null;
  const lastSection = normalizeSavedStockSection(raw.lastSection ?? raw.last_section);
  if (!ticker || !lastSection) return null;

  const addedAt = normalizeDate(raw.addedAt ?? raw.added_at, now);
  const lastVisitedAt = normalizeDate(raw.lastVisitedAt ?? raw.last_visited_at, now);

  return { ticker, addedAt, lastVisitedAt, lastSection };
}

export function sortSavedStocks(items: SavedStock[]): SavedStock[] {
  return [...items].sort((left, right) => {
    const visitedDifference = Date.parse(right.lastVisitedAt) - Date.parse(left.lastVisitedAt);
    return visitedDifference || left.ticker.localeCompare(right.ticker);
  });
}

export function mergeSavedStockRecords(items: SavedStock[]): SavedStock[] {
  const merged = new Map<string, SavedStock>();

  for (const item of items) {
    const normalized = normalizeSavedStock(item);
    if (!normalized) continue;

    const current = merged.get(normalized.ticker);
    if (!current) {
      merged.set(normalized.ticker, normalized);
      continue;
    }

    const incomingIsNewer = Date.parse(normalized.lastVisitedAt) > Date.parse(current.lastVisitedAt);
    merged.set(normalized.ticker, {
      ticker: normalized.ticker,
      addedAt:
        Date.parse(normalized.addedAt) < Date.parse(current.addedAt)
          ? normalized.addedAt
          : current.addedAt,
      lastVisitedAt: incomingIsNewer ? normalized.lastVisitedAt : current.lastVisitedAt,
      lastSection: incomingIsNewer ? normalized.lastSection : current.lastSection,
    });
  }

  return sortSavedStocks([...merged.values()]);
}

function normalizeDate(value: unknown, now: Date): string {
  if (typeof value !== "string") return now.toISOString();
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return now.toISOString();

  // A client clock can be wrong, but it must not push a record arbitrarily far
  // into the future and permanently pin it to the top of the list.
  const maximum = now.getTime() + 5 * 60 * 1000;
  return new Date(Math.min(timestamp, maximum)).toISOString();
}
