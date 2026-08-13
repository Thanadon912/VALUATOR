export type DcfAssumptionValues = {
  growthRate: number;
  perpetualGrowthRate: number;
  discountRate: number;
};

export type ValuationAssumption = DcfAssumptionValues & {
  ticker: string;
  updatedAt: string;
};

export type ValuationAssumptionsSession = {
  authenticated: boolean;
  items: ValuationAssumption[];
  syncStatus: "ready" | "unavailable";
  syncError: string | null;
};

export type ValuationAssumptionsActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; message: string };

export type AssumptionPersistenceResult =
  | { ok: true; persistedTo: "account" | "device" }
  | { ok: false; persistedTo: "device" | "memory"; message: string };
