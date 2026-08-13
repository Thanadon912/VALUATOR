"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LoaderCircle, Search, UserRound } from "lucide-react";

import { SaveStockButton } from "@/features/saved-stocks/save-stock-button";
import { useSavedStocks } from "@/features/saved-stocks/saved-stocks-provider";
import { sectionFromPathname } from "@/features/saved-stocks/validation";

const navigation = [
  ["Summary", "summary"],
  ["News", "news"],
  ["Valuation", "valuation"],
] as const;

export function WorkspaceTopbar({ ticker }: { ticker: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { mode } = useSavedStocks();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || !value) return;

    setError("");
    setLoading(true);

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(value)}`);

      if (!res.ok) {
        let errorMessage = `No matching US ticker found for '${value}'`;
        try {
          const errorData = await res.json();
          if (errorData.error) {
            errorMessage = errorData.error;
          }
        } catch {} // Fallback to default message if JSON parsing fails

        setLoading(false);
        setError(errorMessage);
        return;
      }

      const data = await res.json();
      const symbol = data.symbol;

      if (!symbol) {
        setLoading(false);
        setError(`No matching US ticker found for '${value}'`);
        return;
      }

      router.push(`/stocks/${symbol}/summary`);
      setLoading(false);
    } catch {
      setLoading(false);
      setError(`Failed to search for '${value}'. Please try again.`);
    }
  }

  return (
    <header className="workspace-topbar">
      <div className="workspace-topbar__row">
        <Link className="workspace-brand valuator-wordmark" href="/" aria-label="VALUATOR home">
          <span className="workspace-brand__full">VALUATOR</span>
          <span className="workspace-brand__compact" aria-hidden="true">V</span>
          <span aria-hidden="true" className="workspace-brand__mark" />
        </Link>

        <nav className="workspace-view-nav" aria-label="Stock workspace views">
          {navigation.map(([label, route]) => {
            const active = pathname.endsWith(`/${route}`);
            return (
              <Link
                className={active ? "workspace-view-nav__link workspace-view-nav__link--active" : "workspace-view-nav__link"}
                href={`/stocks/${ticker}/${route}`}
                key={route}
                aria-current={active ? "page" : undefined}
                prefetch
              >
                {label}
              </Link>
            );
          })}
        </nav>

        <form className="workspace-search-form" onSubmit={submit}>
          <div className={`workspace-search ${loading ? "workspace-search--loading" : ""}`}>
            <label className="sr-only" htmlFor="workspace-ticker">
              Search ticker or company
            </label>
            {loading ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Search className="size-4" aria-hidden="true" />
            )}
            <input
              id="workspace-ticker"
              suppressHydrationWarning
              value={value}
              onChange={(event) => {
                const newValue = event.target.value.replace(/[^a-zA-Z0-9\s]/g, "");
                setValue(newValue);
                if (error) setError("");
              }}
              disabled={loading}
              placeholder={`Search ticker or company… (${ticker})`}
              maxLength={10}
            />
          </div>
          {error ? <span className="workspace-search__error" role="alert">{error}</span> : null}
        </form>

        <div className="workspace-topbar__actions">
          <SaveStockButton
            ticker={ticker}
            section={sectionFromPathname(pathname)?.section ?? "summary"}
          />
          <Link
            href={mode === "guest"
              ? `/login?next=${encodeURIComponent(pathname)}`
              : `/account?returnTo=${encodeURIComponent(pathname)}`}
            className="workspace-account-action"
            aria-label={mode === "guest" ? "Sign in" : "Account"}
            title={mode === "guest" ? "Sign in" : "Account"}
          >
            <UserRound className="size-4" aria-hidden="true" />
            <span className="workspace-account-action__label">{mode === "guest" ? "Sign in" : "Account"}</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
