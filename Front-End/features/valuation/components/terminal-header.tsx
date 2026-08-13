import { useState } from "react"
import { fmt } from "@/lib/valuation"

function Telemetry({
  label,
  value,
  sourceUrl,
  asOf,
  role = "Provider fact",
  className = "",
  emphasized = false,
}: {
  label: string
  value: string
  sourceUrl?: string | null
  asOf?: string | null
  role?: "Provider fact" | "Derived output"
  className?: string
  emphasized?: boolean
}) {
  const content = (
    <>
      <span className="text-xs text-[#869E8F]">{label}</span>
      <span className={`mt-0.5 font-mono text-sm font-medium tabular-nums ${emphasized ? "text-emerald-400" : "text-[#E0E6E2]"}`}>{value}</span>
      <span className="mt-0.5 text-[9px] uppercase leading-4 tracking-[0.08em] text-[#6F8577]">{role}{asOf ? ` · ${asOf}` : ""}</span>
    </>
  );
  const baseClass = `flex min-h-[76px] min-w-0 flex-col items-start justify-center px-3 py-2 text-left lg:items-end lg:text-right ${className}`;
  if (sourceUrl?.startsWith("http")) return <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className={`${baseClass} rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#B7FF3C] hover:bg-[#152019] hover:underline`} title={sourceUrl}>{content}</a>
  return <div title={sourceUrl ?? undefined} className={baseClass}>{content}</div>
}

export function TerminalHeader({ 
  tickerSymbol, 
  currentPrice, 
  costOfEquity = null,
  riskFreeRate = null,
  riskFreeRateSource = null,
  riskFreeRateAsOf = null,
  marketCap = null,
  marketCapSource = null,
  beta = null,
  betaSource = null,
  logoUrl,
  fmpLogoUrl,
}: { 
  tickerSymbol: string, 
  currentPrice: number | null,
  costOfEquity?: number | null,
  riskFreeRate?: number | null,
  riskFreeRateSource?: string | null,
  riskFreeRateAsOf?: string | null,
  marketCap?: string | null,
  marketCapSource?: string | null,
  beta?: number | null,
  betaSource?: string | null,
  logoUrl?: string | null,
  fmpLogoUrl?: string | null,
}) {
  const logoDevToken = process.env.NEXT_PUBLIC_LOGO_DEV_TOKEN
  const logoDevUrl = logoDevToken
    ? `https://img.logo.dev/ticker/${tickerSymbol}?token=${logoDevToken}`
    : null
  const primaryLogoUrl = logoUrl || fmpLogoUrl || logoDevUrl
  const backupLogoUrl = logoUrl ? (fmpLogoUrl || logoDevUrl) : logoDevUrl

  const [failedUrls, setFailedUrls] = useState<Set<string>>(new Set())

  const currentUrl = primaryLogoUrl && !failedUrls.has(primaryLogoUrl)
    ? primaryLogoUrl
    : (backupLogoUrl && !failedUrls.has(backupLogoUrl) ? backupLogoUrl : null)

  const handleError = () => {
    if (currentUrl) {
      setFailedUrls((prev) => new Set(prev).add(currentUrl))
    }
  }

  return (
    <header className="border-b border-[#1A2E20] bg-[#0A0D0B]">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-4 md:px-6 lg:flex-row lg:items-center lg:justify-between">
        {/* Left: ticker metadata */}
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-md border border-white/20 bg-white p-1 text-emerald-400">
            {currentUrl ? (
              // Provider-backed URLs retain their existing fallback behavior; no third-party logo is fabricated.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={currentUrl} // Force remount on URL change to re-fire onError if it fails
                src={currentUrl}
                alt={`${tickerSymbol} logo`}
                className="h-full w-full rounded-sm object-contain"
                onError={handleError}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-[#1A2E20] font-mono text-sm font-bold text-[#E0E6E2] rounded-sm">
                {tickerSymbol.slice(0, 2).toUpperCase()}
              </div>
            )}
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <h1 className="font-mono text-lg font-bold tracking-tight text-white">
                {tickerSymbol}
                <span className="sr-only"> valuation dashboard</span>
              </h1>
              <span className="text-sm text-[#869E8F]">| Live Equities</span>
            </div>
            <div className="mt-1 flex items-center gap-3">
              <span className="font-mono text-xl font-semibold tabular-nums text-white">
                {currentPrice === null ? "N/A" : `$${fmt.money(currentPrice)}`}
              </span>
            </div>
          </div>
        </div>

        {/* Right: macro telemetry */}
        <div className="grid w-full grid-cols-2 overflow-hidden rounded-md border border-[#1A2E20] bg-[#111613] lg:w-auto lg:min-w-[640px] lg:grid-cols-4" data-testid="valuation-telemetry-grid">
          <Telemetry
            label="MKT CAP"
            value={marketCap ?? "N/A"}
            sourceUrl={marketCapSource}
            emphasized
            className="border-b border-r border-[#1A2E20] lg:border-b-0"
          />
          <Telemetry
            label="BETA"
            value={beta === null ? "N/A" : beta.toFixed(2)}
            sourceUrl={betaSource}
            className="border-b border-[#1A2E20] lg:border-b-0 lg:border-r"
          />
          <Telemetry
            label="Risk-Free (10Y)"
            value={riskFreeRate === null ? "N/A" : fmt.pct(riskFreeRate)}
            sourceUrl={riskFreeRateSource}
            asOf={riskFreeRateAsOf}
            className="border-r border-[#1A2E20]"
          />
          <Telemetry label="Cost of Equity" value={costOfEquity === null ? "N/A" : fmt.pct(costOfEquity)} role="Derived output" />
        </div>
      </div>
    </header>
  )
}
