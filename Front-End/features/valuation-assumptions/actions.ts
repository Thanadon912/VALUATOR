'use server'

import { hasSupabaseConfig } from "@/lib/supabase/config";
import { createClient } from "@/lib/supabase/server";
import { normalizeTicker } from "@/lib/validation/ticker";

import type {
  ValuationAssumption,
  ValuationAssumptionsActionResult,
  ValuationAssumptionsSession,
} from "./types";
import {
  mergeValuationAssumptions,
  normalizeValuationAssumption,
} from "./validation";

type DatabaseAssumption = {
  ticker: string;
  stage_1_growth_rate: number;
  perpetual_growth_rate: number;
  discount_rate: number;
  updated_at: string;
};

const SELECT_FIELDS = "ticker,stage_1_growth_rate,perpetual_growth_rate,discount_rate,updated_at";
const MAX_SYNC_ITEMS = 100;

export async function listValuationAssumptions(): Promise<
  ValuationAssumptionsActionResult<ValuationAssumptionsSession>
> {
  if (!hasSupabaseConfig()) {
    return {
      ok: true,
      data: { authenticated: false, items: [], syncStatus: "ready", syncError: null },
    };
  }
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return {
        ok: true,
        data: { authenticated: false, items: [], syncStatus: "ready", syncError: null },
      };
    }
    const { data, error } = await supabase
      .from("valuation_assumptions")
      .select(SELECT_FIELDS)
      .order("ticker", { ascending: true });
    if (error) {
      return {
        ok: true,
        data: {
          authenticated: true,
          items: [],
          syncStatus: "unavailable",
          syncError: "Account sync is temporarily unavailable.",
        },
      };
    }
    return {
      ok: true,
      data: {
        authenticated: true,
        items: mapRows((data ?? []) as DatabaseAssumption[]),
        syncStatus: "ready",
        syncError: null,
      },
    };
  } catch {
    return actionError("ASSUMPTIONS_UNAVAILABLE", "Saved assumptions are temporarily unavailable.");
  }
}

export async function saveValuationAssumption(
  input: ValuationAssumption,
): Promise<ValuationAssumptionsActionResult<ValuationAssumption[]>> {
  const normalized = normalizeValuationAssumption(input);
  if (!normalized) return actionError("INVALID_ASSUMPTION", "The DCF assumptions are invalid.");
  return mergeForCurrentUser([normalized]);
}

export async function mergeDeviceValuationAssumptions(
  input: ValuationAssumption[],
): Promise<ValuationAssumptionsActionResult<ValuationAssumption[]>> {
  if (!Array.isArray(input) || input.length > MAX_SYNC_ITEMS) {
    return actionError(
      "ASSUMPTION_LIMIT_EXCEEDED",
      `A maximum of ${MAX_SYNC_ITEMS} valuation assumptions can be synced at once.`,
    );
  }
  const normalized = mergeValuationAssumptions(
    input
      .map((item) => normalizeValuationAssumption(item))
      .filter((item): item is ValuationAssumption => item !== null),
  );
  if (input.length > 0 && normalized.length === 0) {
    return actionError("INVALID_ASSUMPTIONS", "Device assumptions were invalid.");
  }
  if (normalized.length === 0) {
    const session = await listValuationAssumptions();
    if (!session.ok) return session;
    if (!session.data.authenticated) return actionError("AUTH_REQUIRED", "Sign in to sync assumptions.");
    return { ok: true, data: session.data.items };
  }
  return mergeForCurrentUser(normalized);
}

export async function removeValuationAssumption(
  input: string,
): Promise<ValuationAssumptionsActionResult<null>> {
  const ticker = normalizeTicker(input);
  if (!ticker) return actionError("INVALID_TICKER", "The saved assumptions could not be reset.");
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) return actionError("AUTH_REQUIRED", "Sign in to reset synced assumptions.");
    const { error } = await supabase.from("valuation_assumptions").delete().eq("ticker", ticker);
    return error
      ? actionError("ASSUMPTIONS_DELETE_FAILED", "Synced assumptions could not be reset.")
      : { ok: true, data: null };
  } catch {
    return actionError("ASSUMPTIONS_UNAVAILABLE", "Saved assumptions are temporarily unavailable.");
  }
}

async function mergeForCurrentUser(
  items: ValuationAssumption[],
): Promise<ValuationAssumptionsActionResult<ValuationAssumption[]>> {
  try {
    const supabase = await createClient();
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) return actionError("AUTH_REQUIRED", "Sign in to sync assumptions.");
    const payload = items.map((item) => ({
      ticker: item.ticker,
      stage_1_growth_rate: item.growthRate / 100,
      perpetual_growth_rate: item.perpetualGrowthRate / 100,
      discount_rate: item.discountRate / 100,
      updated_at: item.updatedAt,
    }));
    const { error } = await supabase.rpc("merge_valuation_assumptions", { p_items: payload });
    if (error) return actionError("ASSUMPTIONS_SYNC_FAILED", "Assumptions could not be synced.");
    const refreshed = await supabase
      .from("valuation_assumptions")
      .select(SELECT_FIELDS)
      .order("ticker", { ascending: true });
    if (refreshed.error) {
      return actionError("ASSUMPTIONS_READ_FAILED", "Assumptions were synced but could not be reloaded.");
    }
    return { ok: true, data: mapRows((refreshed.data ?? []) as DatabaseAssumption[]) };
  } catch {
    return actionError("ASSUMPTIONS_UNAVAILABLE", "Saved assumptions are temporarily unavailable.");
  }
}

function mapRows(rows: DatabaseAssumption[]): ValuationAssumption[] {
  return mergeValuationAssumptions(
    rows
      .map((row) => normalizeValuationAssumption(row))
      .filter((item): item is ValuationAssumption => item !== null),
  );
}

function actionError<T>(
  code: string,
  message: string,
): ValuationAssumptionsActionResult<T> {
  return { ok: false, code, message };
}
