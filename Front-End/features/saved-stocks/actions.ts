'use server'

import { createClient } from "@/lib/supabase/server";
import { hasSupabaseConfig } from "@/lib/supabase/config";
import { normalizeTicker } from "@/lib/validation/ticker";

import type {
  SavedStock,
  SavedStocksActionResult,
  SavedStocksSession,
} from "./types";
import {
  mergeSavedStockRecords,
  normalizeSavedStock,
  normalizeSavedStockSection,
  sortSavedStocks,
} from "./validation";

type DatabaseSavedStock = {
  ticker: string;
  added_at: string;
  last_visited_at: string;
  last_section: string;
};

const MAX_SYNC_ITEMS = 100;

export async function listSavedStocks(): Promise<SavedStocksActionResult<SavedStocksSession>> {
  if (!hasSupabaseConfig()) {
    return { ok: true, data: { authenticated: false, items: [] } };
  }
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return { ok: true, data: { authenticated: false, items: [] } };
    }

    const { data, error } = await supabase
      .from("saved_stocks")
      .select("ticker,added_at,last_visited_at,last_section")
      .order("last_visited_at", { ascending: false });

    if (error) return actionError("SAVED_STOCKS_READ_FAILED", "Saved stocks could not be loaded.");
    return {
      ok: true,
      data: { authenticated: true, items: mapDatabaseRows(data ?? []) },
    };
  } catch {
    return actionError("SAVED_STOCKS_UNAVAILABLE", "Saved stocks are temporarily unavailable.");
  }
}

export async function saveStock(input: {
  ticker: string;
  lastSection: string;
}): Promise<SavedStocksActionResult<SavedStock[]>> {
  const ticker = normalizeTicker(input.ticker);
  const section = normalizeSavedStockSection(input.lastSection);
  if (!ticker || !section) return actionError("INVALID_SAVED_STOCK", "The stock could not be saved.");

  const now = new Date().toISOString();
  return mergeForCurrentUser([{ ticker, addedAt: now, lastVisitedAt: now, lastSection: section }]);
}

export async function mergeGuestSavedStocks(
  input: SavedStock[],
): Promise<SavedStocksActionResult<SavedStock[]>> {
  if (!Array.isArray(input) || input.length > MAX_SYNC_ITEMS) {
    return actionError(
      "SAVED_STOCK_LIMIT_EXCEEDED",
      `A maximum of ${MAX_SYNC_ITEMS} saved stocks can be synced at once.`,
    );
  }
  const normalized = mergeSavedStockRecords(
    input
      .map((item) => normalizeSavedStock(item))
      .filter((item): item is SavedStock => item !== null),
  );
  if (input.length > 0 && normalized.length === 0) {
    return actionError("INVALID_SAVED_STOCKS", "The saved stocks on this device were invalid.");
  }
  if (normalized.length === 0) {
    const session = await listSavedStocks();
    if (!session.ok) return session;
    if (!session.data.authenticated) return actionError("AUTH_REQUIRED", "Sign in to sync saved stocks.");
    return { ok: true, data: session.data.items };
  }
  return mergeForCurrentUser(normalized);
}

export async function touchSavedStock(input: {
  ticker: string;
  lastSection: string;
}): Promise<SavedStocksActionResult<null>> {
  const ticker = normalizeTicker(input.ticker);
  const section = normalizeSavedStockSection(input.lastSection);
  if (!ticker || !section) return actionError("INVALID_SAVED_STOCK", "The saved stock could not be updated.");

  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) return actionError("AUTH_REQUIRED", "Sign in to sync saved stocks.");

    const { error } = await supabase
      .from("saved_stocks")
      .update({ last_section: section, last_visited_at: new Date().toISOString() })
      .eq("ticker", ticker);
    return error
      ? actionError("SAVED_STOCK_TOUCH_FAILED", "The latest visit could not be synced.")
      : { ok: true, data: null };
  } catch {
    return actionError("SAVED_STOCKS_UNAVAILABLE", "Saved stocks are temporarily unavailable.");
  }
}

export async function removeSavedStock(
  input: string,
): Promise<SavedStocksActionResult<null>> {
  const ticker = normalizeTicker(input);
  if (!ticker) return actionError("INVALID_TICKER", "The stock could not be removed.");

  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) return actionError("AUTH_REQUIRED", "Sign in to sync saved stocks.");

    const { error } = await supabase.from("saved_stocks").delete().eq("ticker", ticker);
    return error
      ? actionError("SAVED_STOCK_REMOVE_FAILED", "The stock could not be removed.")
      : { ok: true, data: null };
  } catch {
    return actionError("SAVED_STOCKS_UNAVAILABLE", "Saved stocks are temporarily unavailable.");
  }
}

async function mergeForCurrentUser(
  items: SavedStock[],
): Promise<SavedStocksActionResult<SavedStock[]>> {
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) return actionError("AUTH_REQUIRED", "Sign in to sync saved stocks.");

    const payload = items.map((item) => ({
      ticker: item.ticker,
      added_at: item.addedAt,
      last_visited_at: item.lastVisitedAt,
      last_section: item.lastSection,
    }));
    const { error } = await supabase.rpc("merge_saved_stocks", { p_items: payload });
    if (error) return actionError("SAVED_STOCK_SYNC_FAILED", "Saved stocks could not be synced.");

    const refreshed = await supabase
      .from("saved_stocks")
      .select("ticker,added_at,last_visited_at,last_section")
      .order("last_visited_at", { ascending: false });
    if (refreshed.error) return actionError("SAVED_STOCKS_READ_FAILED", "Saved stocks were synced but could not be reloaded.");
    return { ok: true, data: mapDatabaseRows(refreshed.data ?? []) };
  } catch {
    return actionError("SAVED_STOCKS_UNAVAILABLE", "Saved stocks are temporarily unavailable.");
  }
}

function mapDatabaseRows(rows: DatabaseSavedStock[]): SavedStock[] {
  const mapped = rows
    .map((row) => normalizeSavedStock(row))
    .filter((item): item is SavedStock => item !== null);
  return sortSavedStocks(mapped);
}

function actionError<T>(code: string, message: string): SavedStocksActionResult<T> {
  return { ok: false, code, message };
}
