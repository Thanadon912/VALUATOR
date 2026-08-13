import type { SavedStock } from "./types";
import { mergeSavedStockRecords, normalizeSavedStock } from "./validation";

export const SAVED_STOCKS_STORAGE_KEY = "valuator:saved-stocks:v1";

type StoredSavedStocks = {
  version: 1;
  items: SavedStock[];
};

export function readGuestSavedStocks(): { items: SavedStock[]; error: string | null } {
  try {
    const raw = window.localStorage.getItem(SAVED_STOCKS_STORAGE_KEY);
    if (!raw) return { items: [], error: null };

    const parsed = JSON.parse(raw) as Partial<StoredSavedStocks>;
    if (parsed.version !== 1 || !Array.isArray(parsed.items)) {
      window.localStorage.removeItem(SAVED_STOCKS_STORAGE_KEY);
      return { items: [], error: "Saved stocks stored on this device were invalid and were reset." };
    }

    const items = parsed.items
      .map((item) => normalizeSavedStock(item))
      .filter((item): item is SavedStock => item !== null);
    const normalized = mergeSavedStockRecords(items);
    if (normalized.length !== parsed.items.length) writeGuestSavedStocks(normalized);
    return { items: normalized, error: null };
  } catch {
    return {
      items: [],
      error: "Saved stocks are unavailable because this browser blocked device storage.",
    };
  }
}

export function writeGuestSavedStocks(items: SavedStock[]): boolean {
  try {
    if (items.length === 0) {
      window.localStorage.removeItem(SAVED_STOCKS_STORAGE_KEY);
      return true;
    }

    const payload: StoredSavedStocks = {
      version: 1,
      items: mergeSavedStockRecords(items),
    };
    window.localStorage.setItem(SAVED_STOCKS_STORAGE_KEY, JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

export function clearGuestSavedStocks(): boolean {
  try {
    window.localStorage.removeItem(SAVED_STOCKS_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}
