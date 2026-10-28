"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LoaderCircle } from "lucide-react";
import { useTickerSearch } from "./use-ticker-search";

export function LandingSearch() {
  const router = useRouter();
  const {
    query: ticker,
    handleInputChange,
    error,
    loading: submitting,
    handleSubmit: submit,
  } = useTickerSearch({
    onSuccess: (symbol) => {
      router.push(`/stocks/${symbol}/valuation`);
    },
  });

  return (
    <form className="w-full" onSubmit={submit} noValidate>
      <label className="sr-only" htmlFor="landing-ticker">
        Ticker or company name
      </label>
      <div className="valuator-search flex flex-col gap-3 sm:flex-row">
        <div className={`valuator-search-input-wrapper relative flex-1 min-w-0 overflow-hidden rounded-md ${submitting ? "valuator-search-input-wrapper--loading" : ""}`}>
          <input
            id="landing-ticker"
            value={ticker}
            onChange={(event) => handleInputChange(event.target.value)}
            placeholder="AAPL or Apple"
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            maxLength={64}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "landing-ticker-error" : "landing-ticker-hint"}
            className={`valuator-search-input min-h-14 w-full border bg-[#050505] px-5 text-base font-semibold uppercase text-[#F2F2EE] placeholder:normal-case placeholder:font-normal placeholder:text-[#8C8C86] focus:outline-none ${error ? "valuator-search-input--error" : "border-white/25"}`}
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className={`valuator-search-submit relative min-h-14 overflow-hidden border border-[#B7FF3C] bg-[#B7FF3C] px-7 text-sm font-bold text-[#050505] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505] disabled:cursor-wait ${submitting ? "valuator-search-submit--loading" : ""}`}
        >
          <span className="relative z-10 inline-flex items-center justify-center gap-2">
            {submitting ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
            {submitting ? "Opening workspace…" : "Open analysis"}
          </span>
        </button>
      </div>
      {error ? <p id="landing-ticker-error" role="alert" className="valuator-search-error mt-2 text-sm font-medium text-[#FF8E7A]">{error} Try a symbol such as AAPL or BRK.B.</p> : <p id="landing-ticker-hint" className="mt-2 text-sm text-[#92928C]">Letters, numbers, periods, and hyphens are supported.</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-[#92928C]">
        <span>Try</span>
        {["AAPL", "MSFT", "NVDA"].map((example) => (
          <Link key={example} href={`/stocks/${example}/valuation`} className="valuator-example-link relative min-h-11 content-center px-2 font-mono font-semibold text-[#D5D5CE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">{example}</Link>
        ))}
      </div>
    </form>
  );
}
