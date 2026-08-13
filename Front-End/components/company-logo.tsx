"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

// Maps a ticker to its primary domain so we can resolve a brand mark.
// Swap `buildLogoUrl` to the logo.dev API later, e.g.:
//   `https://img.logo.dev/ticker/${ticker}?token=YOUR_PUBLISHABLE_KEY&size=64`
export const TICKER_DOMAINS: Record<string, string> = {
  AAPL: "apple.com",
  TSLA: "tesla.com",
  NVDA: "nvidia.com",
  MSFT: "microsoft.com",
  AMZN: "amazon.com",
  GOOGL: "abc.xyz",
  META: "meta.com",
  AMD: "amd.com",
  NFLX: "netflix.com",
  JPM: "jpmorganchase.com",
  BABA: "alibaba.com",
}

function buildLogoUrl(ticker: string) {
  const token = process.env.NEXT_PUBLIC_LOGO_DEV_TOKEN
  if (!token) return null
  return `https://img.logo.dev/ticker/${ticker}?token=${token}`
}

type CompanyLogoProps = {
  ticker: string
  className?: string
}

export function CompanyLogo({ ticker, className }: CompanyLogoProps) {
  const [failed, setFailed] = useState(false)
  const src = buildLogoUrl(ticker)

  if (!src || failed) {
    return (
      <span
        className={cn(
          "flex items-center justify-center rounded-xl border border-white/10 bg-white/10 font-mono text-[9px] font-semibold text-slate-300",
          className,
        )}
        aria-hidden="true"
      >
        {ticker.charAt(0)}
      </span>
    )
  }

  return (
    <div className={cn("flex items-center justify-center overflow-hidden rounded-xl border border-white/20 bg-white p-1", className)}>
      {/* Provider URLs vary at runtime, so the native image keeps the existing error fallback. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src || "/placeholder.svg"}
        alt=""
        aria-hidden="true"
        loading="lazy"
        crossOrigin="anonymous"
        onError={() => setFailed(true)}
        className="h-full w-full rounded-md object-contain"
      />
    </div>
  )
}
