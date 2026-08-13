import { normalizeTicker } from "@/lib/validation/ticker";

import type { DcfAssumptionValues, ValuationAssumption } from "./types";

export function validateDcfAssumptionValues(
  value: DcfAssumptionValues,
): boolean {
  return (
    Number.isFinite(value.growthRate) &&
    value.growthRate >= 0 &&
    Number.isFinite(value.perpetualGrowthRate) &&
    value.perpetualGrowthRate >= 1 &&
    value.perpetualGrowthRate <= 4 &&
    Number.isFinite(value.discountRate) &&
    value.discountRate >= 5 &&
    value.discountRate <= 15 &&
    value.discountRate > value.perpetualGrowthRate
  );
}

export function normalizeValuationAssumption(
  value: unknown,
  now = new Date(),
): ValuationAssumption | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const ticker = typeof raw.ticker === "string" ? normalizeTicker(raw.ticker) : null;
  if (!ticker) return null;

  const values: DcfAssumptionValues = {
    growthRate: numberValue(raw.growthRate ?? raw.stage_1_growth_rate, raw.growthRate === undefined),
    perpetualGrowthRate: numberValue(
      raw.perpetualGrowthRate ?? raw.perpetual_growth_rate,
      raw.perpetualGrowthRate === undefined,
    ),
    discountRate: numberValue(raw.discountRate ?? raw.discount_rate, raw.discountRate === undefined),
  };
  if (!validateDcfAssumptionValues(values)) return null;

  return {
    ticker,
    ...values,
    updatedAt: normalizeDate(raw.updatedAt ?? raw.updated_at, now),
  };
}

export function mergeValuationAssumptions(
  items: ValuationAssumption[],
): ValuationAssumption[] {
  const merged = new Map<string, ValuationAssumption>();
  for (const item of items) {
    const normalized = normalizeValuationAssumption(item);
    if (!normalized) continue;
    const current = merged.get(normalized.ticker);
    if (!current || Date.parse(normalized.updatedAt) >= Date.parse(current.updatedAt)) {
      merged.set(normalized.ticker, normalized);
    }
  }
  return [...merged.values()].sort((left, right) =>
    left.ticker.localeCompare(right.ticker),
  );
}

function numberValue(value: unknown, databaseDecimal: boolean): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return Number.NaN;
  return databaseDecimal ? value * 100 : value;
}

function normalizeDate(value: unknown, now: Date): string {
  if (typeof value !== "string") return now.toISOString();
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return now.toISOString();
  return new Date(Math.min(parsed, now.getTime() + 5 * 60 * 1000)).toISOString();
}
