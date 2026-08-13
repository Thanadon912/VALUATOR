"use client";

import { Bookmark, LoaderCircle } from "lucide-react";
import { useState } from "react";

import type { SavedStockSection } from "./types";
import { useSavedStocks } from "./saved-stocks-provider";

export function SaveStockButton({
  ticker,
  section,
  compact = false,
}: {
  ticker: string;
  section: SavedStockSection;
  compact?: boolean;
}) {
  const { isSaved, toggle } = useSavedStocks();
  const [pending, setPending] = useState(false);
  const saved = isSaved(ticker);

  const handleClick = async () => {
    if (pending) return;
    setPending(true);
    try {
      await toggle(ticker, section);
    } finally {
      setPending(false);
    }
  };

  return (
    <button
      type="button"
      aria-label={`${saved ? "Remove" : "Save"} ${ticker} ${saved ? "from" : "to"} saved stocks`}
      aria-pressed={saved}
      title={saved ? `Remove ${ticker} from saved stocks` : `Save ${ticker} to saved stocks`}
      disabled={pending}
      onClick={handleClick}
      className="workspace-save-action inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-[13px] font-semibold text-[#C8D4CC] transition-colors hover:bg-[#B7FF3C]/8 hover:text-[#EFFAF4] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] disabled:opacity-60"
    >
      {pending ? (
        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        <Bookmark className={`size-4 ${saved ? "fill-[#B7FF3C] text-[#B7FF3C]" : "text-[#90B09E]"}`} aria-hidden="true" />
      )}
      {compact ? null : <span className="workspace-save-action__label">{saved ? "Saved" : "Save"}</span>}
    </button>
  );
}
