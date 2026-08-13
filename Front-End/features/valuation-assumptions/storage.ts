import type { ValuationAssumption } from "./types";
import { mergeValuationAssumptions, normalizeValuationAssumption } from "./validation";

export const VALUATION_ASSUMPTIONS_STORAGE_KEY = "valuator:valuation-assumptions:v1";

type StoredAssumptions = {
  version: 1;
  items: ValuationAssumption[];
};

export function readDeviceAssumptions(): {
  items: ValuationAssumption[];
  error: string | null;
} {
  try {
    const raw = window.localStorage.getItem(VALUATION_ASSUMPTIONS_STORAGE_KEY);
    if (!raw) return { items: [], error: null };
    const parsed = JSON.parse(raw) as Partial<StoredAssumptions>;
    if (parsed.version !== 1 || !Array.isArray(parsed.items)) {
      window.localStorage.removeItem(VALUATION_ASSUMPTIONS_STORAGE_KEY);
      return { items: [], error: "Saved assumptions were invalid and were reset." };
    }
    const items = parsed.items
      .map((item) => normalizeValuationAssumption(item))
      .filter((item): item is ValuationAssumption => item !== null);
    const normalized = mergeValuationAssumptions(items);
    if (normalized.length !== parsed.items.length) writeDeviceAssumptions(normalized);
    return { items: normalized, error: null };
  } catch {
    return {
      items: [],
      error: "This browser blocked storage for valuation assumptions.",
    };
  }
}

export function writeDeviceAssumptions(items: ValuationAssumption[]): boolean {
  try {
    if (items.length === 0) {
      window.localStorage.removeItem(VALUATION_ASSUMPTIONS_STORAGE_KEY);
      return true;
    }
    const payload: StoredAssumptions = {
      version: 1,
      items: mergeValuationAssumptions(items),
    };
    window.localStorage.setItem(
      VALUATION_ASSUMPTIONS_STORAGE_KEY,
      JSON.stringify(payload),
    );
    return true;
  } catch {
    return false;
  }
}

export function removeDeviceAssumption(ticker: string): boolean {
  const stored = readDeviceAssumptions();
  return writeDeviceAssumptions(
    stored.items.filter((item) => item.ticker !== ticker.toUpperCase()),
  );
}
