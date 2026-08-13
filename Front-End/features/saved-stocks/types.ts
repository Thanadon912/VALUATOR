export const SAVED_STOCK_SECTIONS = ["summary", "news", "valuation"] as const;

export type SavedStockSection = (typeof SAVED_STOCK_SECTIONS)[number];

export type SavedStock = {
  ticker: string;
  addedAt: string;
  lastVisitedAt: string;
  lastSection: SavedStockSection;
};

export type SavedStocksSession = {
  authenticated: boolean;
  items: SavedStock[];
};

export type SavedStockSnapshot = {
  ticker: string;
  company_name: string | null;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  currency: string | null;
  status: string;
  as_of: string | null;
  sources: Array<{
    provider: string;
    source_url: string | null;
    source_timestamp: string | null;
    fetched_at: string;
    is_stale: boolean;
  }>;
  warnings: string[];
};

export type SavedStockSnapshotsResponse = {
  status: string;
  as_of: string | null;
  data: SavedStockSnapshot[];
  warnings: string[];
};

export type SavedStocksActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; message: string };
