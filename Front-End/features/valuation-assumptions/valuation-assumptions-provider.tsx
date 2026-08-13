"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  listValuationAssumptions,
  mergeDeviceValuationAssumptions,
  removeValuationAssumption,
  saveValuationAssumption,
} from "./actions";
import {
  readDeviceAssumptions,
  removeDeviceAssumption,
  VALUATION_ASSUMPTIONS_STORAGE_KEY,
  writeDeviceAssumptions,
} from "./storage";
import type {
  AssumptionPersistenceResult,
  DcfAssumptionValues,
  ValuationAssumption,
  ValuationAssumptionsSession,
} from "./types";
import { mergeValuationAssumptions } from "./validation";

type Mode = "loading" | "guest" | "authenticated";

const SYNC_RETRY_DELAYS_MS = [1_000, 3_000, 10_000] as const;
const SYNC_UNAVAILABLE_MESSAGE =
  "Account sync is temporarily unavailable. Your assumptions remain active on this device. We'll retry automatically.";

type ContextValue = {
  mode: Mode;
  loading: boolean;
  error: string | null;
  get: (ticker: string) => ValuationAssumption | null;
  save: (ticker: string, values: DcfAssumptionValues) => Promise<AssumptionPersistenceResult>;
  remove: (ticker: string) => Promise<{ ok: boolean; message?: string }>;
  retry: () => Promise<void>;
};

const ValuationAssumptionsContext = createContext<ContextValue | null>(null);

export function ValuationAssumptionsProvider({
  children,
  initialSession,
}: {
  children: React.ReactNode;
  initialSession: ValuationAssumptionsSession | null;
}) {
  const pathname = usePathname();
  const initialItems = initialSession?.items ?? [];
  const initialMode: Mode = initialSession
    ? initialSession.authenticated ? "authenticated" : "guest"
    : "loading";
  const [items, setItems] = useState(initialItems);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [error, setError] = useState<string | null>(initialSession?.syncError ?? null);
  const itemsRef = useRef(initialItems);
  const modeRef = useRef(initialMode);
  const hydrateRequestRef = useRef(0);
  const hydrateRef = useRef<() => Promise<void>>(async () => undefined);
  const retryAttemptRef = useRef(0);
  const retryTimerRef = useRef<number | null>(null);

  const clearScheduledRetry = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const scheduleRetry = useCallback(() => {
    clearScheduledRetry();
    if (retryAttemptRef.current >= SYNC_RETRY_DELAYS_MS.length) return;
    const delay = SYNC_RETRY_DELAYS_MS[retryAttemptRef.current];
    retryAttemptRef.current += 1;
    retryTimerRef.current = window.setTimeout(() => {
      retryTimerRef.current = null;
      void hydrateRef.current();
    }, delay);
  }, [clearScheduledRetry]);

  const replaceItems = useCallback((next: ValuationAssumption[]) => {
    const normalized = mergeValuationAssumptions(next);
    itemsRef.current = normalized;
    setItems(normalized);
    return normalized;
  }, []);

  const replaceMode = useCallback((next: Mode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  const hydrate = useCallback(async () => {
    const requestId = ++hydrateRequestRef.current;
    const local = readDeviceAssumptions();
    if (modeRef.current !== "authenticated" && local.items.length > 0) {
      replaceItems(local.items);
    }
    if (local.error) setError(local.error);

    const session = await listValuationAssumptions();
    if (requestId !== hydrateRequestRef.current) return;
    if (!session.ok) {
      if (modeRef.current === "loading") replaceMode("guest");
      if (modeRef.current === "authenticated") {
        setError(SYNC_UNAVAILABLE_MESSAGE);
        scheduleRetry();
      } else {
        setError(session.message);
      }
      return;
    }
    if (!session.data.authenticated) {
      replaceMode("guest");
      replaceItems(local.items);
      setError(local.error);
      clearScheduledRetry();
      retryAttemptRef.current = 0;
      return;
    }

    replaceMode("authenticated");
    if (session.data.syncStatus === "unavailable") {
      if (local.items.length > 0) {
        replaceItems([...itemsRef.current, ...local.items]);
      }
      setError(SYNC_UNAVAILABLE_MESSAGE);
      scheduleRetry();
      return;
    }
    clearScheduledRetry();
    retryAttemptRef.current = 0;
    if (local.items.length === 0) {
      replaceItems(session.data.items);
      setError(null);
      return;
    }
    const reconciled = mergeValuationAssumptions([...session.data.items, ...local.items]);
    replaceItems(reconciled);
    if (sameItems(reconciled, session.data.items)) {
      writeDeviceAssumptions([]);
      setError(null);
      return;
    }
    const merged = await mergeDeviceValuationAssumptions(local.items);
    if (requestId !== hydrateRequestRef.current) return;
    if (!merged.ok) {
      setError(`${merged.message} The device copy was kept so you can retry.`);
      scheduleRetry();
      return;
    }
    replaceItems(merged.data);
    writeDeviceAssumptions([]);
    setError(null);
  }, [clearScheduledRetry, replaceItems, replaceMode, scheduleRetry]);

  useEffect(() => {
    hydrateRef.current = hydrate;
  }, [hydrate]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void hydrate(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      hydrateRequestRef.current += 1;
    };
  }, [hydrate, pathname]);

  useEffect(() => () => clearScheduledRetry(), [clearScheduledRetry]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== VALUATION_ASSUMPTIONS_STORAGE_KEY || modeRef.current !== "guest") return;
      const stored = readDeviceAssumptions();
      replaceItems(stored.items);
      if (stored.error) setError(stored.error);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [replaceItems]);

  useEffect(() => {
    const handleFocus = () => {
      if (modeRef.current === "authenticated") {
        clearScheduledRetry();
        retryAttemptRef.current = 0;
        void hydrate();
      }
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [clearScheduledRetry, hydrate]);

  const save = useCallback(async (
    ticker: string,
    values: DcfAssumptionValues,
  ): Promise<AssumptionPersistenceResult> => {
    const record: ValuationAssumption = {
      ticker: ticker.toUpperCase(),
      ...values,
      updatedAt: new Date().toISOString(),
    };
    replaceItems([
      ...itemsRef.current.filter((item) => item.ticker !== record.ticker),
      record,
    ]);
    const stored = writeDeviceAssumptions([
      ...readDeviceAssumptions().items.filter((item) => item.ticker !== record.ticker),
      record,
    ]);
    setError(null);

    if (modeRef.current !== "authenticated") {
      if (stored) return { ok: true, persistedTo: "device" };
      const message = "The assumptions are applied for this visit, but device storage is blocked.";
      setError(message);
      return { ok: false, persistedTo: "memory", message };
    }

    const result = await saveValuationAssumption(record);
    if (!result.ok) {
      const message = stored
        ? `${result.message} The device copy was kept so you can retry.`
        : result.message;
      setError(message);
      scheduleRetry();
      return { ok: false, persistedTo: stored ? "device" : "memory", message };
    }
    replaceItems(result.data);
    removeDeviceAssumption(record.ticker);
    setError(null);
    return { ok: true, persistedTo: "account" };
  }, [replaceItems, scheduleRetry]);

  const remove = useCallback(async (ticker: string) => {
    const normalizedTicker = ticker.toUpperCase();
    if (modeRef.current === "authenticated") {
      const result = await removeValuationAssumption(normalizedTicker);
      if (!result.ok) {
        setError(result.message);
        return { ok: false, message: result.message };
      }
    }
    replaceItems(itemsRef.current.filter((item) => item.ticker !== normalizedTicker));
    const removed = removeDeviceAssumption(normalizedTicker);
    if (!removed) {
      const message = "The model was reset, but the device copy could not be cleared.";
      setError(message);
      return { ok: true, message };
    }
    setError(null);
    return { ok: true };
  }, [replaceItems]);

  const value = useMemo<ContextValue>(() => ({
    mode,
    loading: mode === "loading",
    error,
    get: (ticker) => items.find((item) => item.ticker === ticker.toUpperCase()) ?? null,
    save,
    remove,
    retry: async () => {
      clearScheduledRetry();
      retryAttemptRef.current = 0;
      await hydrate();
    },
  }), [clearScheduledRetry, error, hydrate, items, mode, remove, save]);

  return (
    <ValuationAssumptionsContext.Provider value={value}>
      {children}
    </ValuationAssumptionsContext.Provider>
  );
}

export function useValuationAssumptions(): ContextValue {
  const value = useContext(ValuationAssumptionsContext);
  if (!value) throw new Error("useValuationAssumptions must be used inside ValuationAssumptionsProvider");
  return value;
}

function sameItems(left: ValuationAssumption[], right: ValuationAssumption[]) {
  return JSON.stringify(mergeValuationAssumptions(left)) === JSON.stringify(mergeValuationAssumptions(right));
}
