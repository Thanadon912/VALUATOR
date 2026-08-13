"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

const CHECK_INTERVAL_MS = 5 * 60 * 1_000;

export function ReleaseFreshness({ currentRevision }: { currentRevision: string }) {
  const pathname = usePathname();
  const [newRevision, setNewRevision] = useState<string | null>(null);
  const checkingRef = useRef(false);

  const check = useCallback(async () => {
    if (checkingRef.current || newRevision) return;
    checkingRef.current = true;
    try {
      const response = await fetch("/api/release", { cache: "no-store" });
      if (!response.ok) return;
      const payload = await response.json() as { revision?: unknown };
      if (
        typeof payload.revision === "string" &&
        payload.revision.length > 0 &&
        payload.revision !== currentRevision
      ) {
        setNewRevision(payload.revision);
      }
    } catch {
      // A freshness check must never interrupt the active analysis.
    } finally {
      checkingRef.current = false;
    }
  }, [currentRevision, newRevision]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void check(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [check, pathname]);

  useEffect(() => {
    const handleFocus = () => void check();
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void check();
    };
    const intervalId = window.setInterval(() => void check(), CHECK_INTERVAL_MS);
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [check]);

  if (!newRevision) return null;

  return (
    <aside
      role="status"
      className="fixed inset-x-3 bottom-3 z-[100] mx-auto flex max-w-xl items-center justify-between gap-4 rounded-[10px] border border-[#B7FF3C]/40 bg-[#10150F] px-4 py-3 text-sm text-[#EFFAF4] shadow-2xl shadow-black/60"
    >
      <span>New version available. Reload to use the latest fixes.</span>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="min-h-11 shrink-0 rounded-[8px] bg-[#B7FF3C] px-4 font-semibold text-[#071008] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
      >
        Reload now
      </button>
    </aside>
  );
}
