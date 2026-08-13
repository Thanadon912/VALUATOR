"use client";

import Link from "next/link";
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
  listSavedStocks,
  mergeGuestSavedStocks,
  removeSavedStock,
  saveStock,
  touchSavedStock,
} from "./actions";
import {
  clearGuestSavedStocks,
  readGuestSavedStocks,
  SAVED_STOCKS_STORAGE_KEY,
  writeGuestSavedStocks,
} from "./storage";
import type { SavedStock, SavedStockSection, SavedStocksSession } from "./types";
import { mergeSavedStockRecords, sectionFromPathname } from "./validation";

type SavedStocksMode = "loading" | "guest" | "authenticated";

type SavedStocksContextValue = {
  items: SavedStock[];
  mode: SavedStocksMode;
  loading: boolean;
  error: string | null;
  isSaved: (ticker: string) => boolean;
  toggle: (ticker: string, section: SavedStockSection) => Promise<void>;
  remove: (ticker: string) => Promise<boolean>;
  restore: (item: SavedStock) => Promise<boolean>;
  retrySync: () => Promise<void>;
};

const SavedStocksContext = createContext<SavedStocksContextValue | null>(null);

export function SavedStocksProvider({
  children,
  initialSession,
}: {
  children: React.ReactNode;
  initialSession: SavedStocksSession | null;
}) {
  const pathname = usePathname();
  const initialItems = initialSession?.items ?? [];
  const initialMode: SavedStocksMode = initialSession
    ? initialSession.authenticated
      ? "authenticated"
      : "guest"
    : "loading";
  const [items, setItems] = useState<SavedStock[]>(initialItems);
  const [mode, setMode] = useState<SavedStocksMode>(initialMode);
  const [error, setError] = useState<string | null>(null);
  const [guestNotice, setGuestNotice] = useState<string | null>(null);
  const itemsRef = useRef<SavedStock[]>(initialItems);
  const modeRef = useRef<SavedStocksMode>(initialMode);
  const hydrateRequestRef = useRef(0);

  const replaceItems = useCallback((next: SavedStock[]) => {
    const normalized = mergeSavedStockRecords(next);
    itemsRef.current = normalized;
    setItems(normalized);
    return normalized;
  }, []);

  const replaceMode = useCallback((next: SavedStocksMode) => {
    modeRef.current = next;
    setMode(next);
  }, []);

  const persistGuest = useCallback((next: SavedStock[]) => {
    if (!writeGuestSavedStocks(next)) {
      setError("Saved stocks are available for this visit, but this browser blocked device storage.");
      return false;
    }
    return true;
  }, []);

  const hydrate = useCallback(async () => {
    const requestId = ++hydrateRequestRef.current;
    const local = readGuestSavedStocks();
    if (modeRef.current !== "authenticated" && local.items.length > 0) {
      replaceItems(local.items);
    }
    if (local.error) setError(local.error);

    const session = await listSavedStocks();
    if (requestId !== hydrateRequestRef.current) return;

    if (!session.ok) {
      if (modeRef.current === "loading") replaceMode("guest");
      setError(session.message);
      return;
    }

    if (!session.data.authenticated) {
      replaceMode("guest");
      replaceItems(local.items);
      setError(local.error);
      return;
    }

    replaceMode("authenticated");
    if (local.items.length === 0) {
      replaceItems(session.data.items);
      setError(null);
      return;
    }

    const reconciled = mergeSavedStockRecords([
      ...session.data.items,
      ...local.items,
    ]);
    replaceItems(reconciled);

    // A stale guest copy that contributes no newer or missing record is safe
    // to discard without another database write.
    if (sameSavedStocks(reconciled, session.data.items)) {
      setError(
        clearGuestSavedStocks()
          ? null
          : "Your account is synced, but the duplicate device copy could not be cleared.",
      );
      return;
    }

    const merged = await mergeGuestSavedStocks(local.items);
    if (requestId !== hydrateRequestRef.current) return;
    if (!merged.ok) {
      setError(`${merged.message} Your device copy was kept so you can retry.`);
      return;
    }

    replaceItems(merged.data);
    setError(
      clearGuestSavedStocks()
        ? null
        : "Cloud sync succeeded, but the guest copy could not be cleared from this device.",
    );
  }, [replaceItems, replaceMode]);

  useEffect(() => {
    // Server-action auth redirects keep the root layout mounted. Re-check the
    // session when the route changes so a just-created/login session merges
    // guest stocks, and logout immediately drops cloud-owned data from memory.
    const timeoutId = window.setTimeout(() => void hydrate(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      hydrateRequestRef.current += 1;
    };
  }, [hydrate, pathname]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== SAVED_STOCKS_STORAGE_KEY || modeRef.current !== "guest") return;
      const stored = readGuestSavedStocks();
      replaceItems(stored.items);
      if (stored.error) setError(stored.error);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [replaceItems]);

  useEffect(() => {
    const refreshOnFocus = () => {
      if (modeRef.current !== "authenticated") return;
      void hydrate();
    };
    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, [hydrate]);

  useEffect(() => {
    const route = sectionFromPathname(pathname);
    if (!route) return;
    const current = itemsRef.current.find((item) => item.ticker === route.ticker);
    if (!current || current.lastSection === route.section && Date.now() - Date.parse(current.lastVisitedAt) < 1_000) {
      return;
    }

    const updated: SavedStock = {
      ...current,
      lastSection: route.section,
      lastVisitedAt: new Date().toISOString(),
    };
    const next = replaceItems([
      ...itemsRef.current.filter((item) => item.ticker !== route.ticker),
      updated,
    ]);

    if (modeRef.current === "guest") {
      persistGuest(next);
    } else if (modeRef.current === "authenticated") {
      updatePendingGuestRecord(updated);
      void touchSavedStock({ ticker: route.ticker, lastSection: route.section }).then((result) => {
        if (!result.ok) setError(result.message);
      });
    }
  }, [pathname, items, persistGuest, replaceItems]);

  const toggle = useCallback(async (ticker: string, section: SavedStockSection) => {
    const previous = itemsRef.current;
    const existing = previous.find((item) => item.ticker === ticker);
    const now = new Date().toISOString();
    const optimistic = existing
      ? previous.filter((item) => item.ticker !== ticker)
      : [{ ticker, addedAt: now, lastVisitedAt: now, lastSection: section }, ...previous];

    const next = replaceItems(optimistic);
    setError(null);

    if (modeRef.current !== "authenticated") {
      persistGuest(next);
      setGuestNotice(existing ? null : ticker);
      return;
    }

    if (existing) {
      removePendingGuestRecord(ticker);
      const result = await removeSavedStock(ticker);
      if (!result.ok) {
        replaceItems(previous);
        setError(result.message);
      }
      return;
    }

    const result = await saveStock({ ticker, lastSection: section });
    if (!result.ok) {
      replaceItems(previous);
      setError(result.message);
      return;
    }
    replaceItems(result.data);
  }, [persistGuest, replaceItems]);

  const remove = useCallback(async (ticker: string) => {
    if (!itemsRef.current.some((item) => item.ticker === ticker)) return false;
    const previous = itemsRef.current;
    const next = replaceItems(previous.filter((item) => item.ticker !== ticker));
    setError(null);

    if (modeRef.current !== "authenticated") {
      if (persistGuest(next)) return true;
      replaceItems(previous);
      return false;
    }

    removePendingGuestRecord(ticker);
    const result = await removeSavedStock(ticker);
    if (!result.ok) {
      replaceItems(previous);
      setError(result.message);
      return false;
    }
    return true;
  }, [persistGuest, replaceItems]);

  const restore = useCallback(async (item: SavedStock) => {
    const previous = itemsRef.current;
    const next = replaceItems([
      ...previous.filter((current) => current.ticker !== item.ticker),
      item,
    ]);
    setError(null);

    if (modeRef.current !== "authenticated") {
      if (persistGuest(next)) return true;
      replaceItems(previous);
      return false;
    }

    const result = await mergeGuestSavedStocks([item]);
    if (!result.ok) {
      replaceItems(previous);
      setError(result.message);
      return false;
    }
    replaceItems(result.data);
    return true;
  }, [persistGuest, replaceItems]);

  const retrySync = useCallback(async () => {
    await hydrate();
  }, [hydrate]);

  const value = useMemo<SavedStocksContextValue>(() => ({
    items,
    mode,
    loading: mode === "loading",
    error,
    isSaved: (ticker) => items.some((item) => item.ticker === ticker),
    toggle,
    remove,
    restore,
    retrySync,
  }), [error, items, mode, remove, restore, retrySync, toggle]);

  return (
    <SavedStocksContext.Provider value={value}>
      {children}
      {guestNotice ? (
        <aside
          className="fixed bottom-4 left-1/2 z-[80] flex w-[min(92vw,34rem)] -translate-x-1/2 flex-col gap-3 rounded-xl border border-[#B7FF3C]/25 bg-[#0B0F0D]/95 p-4 text-sm text-[#EFFAF4] shadow-2xl backdrop-blur-md sm:flex-row sm:items-center"
          role="status"
          aria-live="polite"
        >
          <p className="min-w-0 flex-1">
            <strong>{guestNotice}</strong> saved on this device. Create an account to sync across devices.
          </p>
          <div className="flex shrink-0 gap-2">
            <Link
              href={`/register?next=${encodeURIComponent(pathname)}`}
              className="inline-flex min-h-11 items-center rounded-lg bg-[#B7FF3C] px-3 font-semibold text-[#050505] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              Create account
            </Link>
            <button
              type="button"
              onClick={() => setGuestNotice(null)}
              className="min-h-11 rounded-lg border border-white/15 px-3 font-semibold text-[#D1D1CA] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
            >
              Not now
            </button>
          </div>
        </aside>
      ) : null}
    </SavedStocksContext.Provider>
  );
}

function sameSavedStocks(left: SavedStock[], right: SavedStock[]): boolean {
  const normalizedLeft = mergeSavedStockRecords(left);
  const normalizedRight = mergeSavedStockRecords(right);
  return JSON.stringify(normalizedLeft) === JSON.stringify(normalizedRight);
}

function removePendingGuestRecord(ticker: string): void {
  const local = readGuestSavedStocks();
  if (!local.items.some((item) => item.ticker === ticker)) return;
  writeGuestSavedStocks(local.items.filter((item) => item.ticker !== ticker));
}

function updatePendingGuestRecord(record: SavedStock): void {
  const local = readGuestSavedStocks();
  if (!local.items.some((item) => item.ticker === record.ticker)) return;
  writeGuestSavedStocks([
    ...local.items.filter((item) => item.ticker !== record.ticker),
    record,
  ]);
}

export function useSavedStocks(): SavedStocksContextValue {
  const value = useContext(SavedStocksContext);
  if (!value) throw new Error("useSavedStocks must be used inside SavedStocksProvider");
  return value;
}
