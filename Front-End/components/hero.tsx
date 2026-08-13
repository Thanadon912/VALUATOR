"use client"

import { ArrowDownRight } from "lucide-react"
import { useEffect, useRef } from "react"
import { LandingSearch } from "@/features/ticker-search/landing-search"
import { SavedStocksPanel } from "@/features/saved-stocks/saved-stocks-panel"
import { useSavedStocks } from "@/features/saved-stocks/saved-stocks-provider"

export function Hero() {
  const { mode } = useSavedStocks()

  if (mode === "authenticated") return <AuthenticatedLauncher />
  if (mode === "loading") return <LandingLoadingShell />
  return <PublicHero />
}

function AuthenticatedLauncher() {
  return (
    <section
      id="find-fair-value"
      className="valuator-hero relative scroll-mt-24 border-b border-white/10"
    >
      <div aria-hidden="true" className="valuator-coordinate-grid absolute inset-0" />
      <div className="relative mx-auto max-w-[90rem] px-5 py-10 sm:px-8 sm:py-12 lg:py-14">
        <div className="grid items-end gap-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(28rem,1.15fr)] lg:gap-14">
          <div>
            <p className="text-sm font-semibold text-[#B7FF3C]">Your research workspace</p>
            <h1 className="valuator-display mt-3 max-w-[15ch] text-4xl font-semibold leading-[0.96] tracking-[-0.035em] text-[#F2F2EE] sm:text-5xl">
              Continue your valuation work.
            </h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-[#A6A69F]">
              Open a ticker or return to the company and section you last visited.
            </p>
          </div>

          <div>
            <LandingSearch />
            <p className="mt-4 max-w-2xl text-sm leading-6 text-[#A6A69F]">
              No valuation is calculated until required provider inputs are returned and validated.
            </p>
          </div>
        </div>

        <div className="mt-10">
          <SavedStocksPanel />
        </div>
      </div>
    </section>
  )
}

function LandingLoadingShell() {
  return (
    <section
      id="find-fair-value"
      aria-busy="true"
      className="valuator-hero relative scroll-mt-24 border-b border-white/10"
    >
      <div aria-hidden="true" className="valuator-coordinate-grid absolute inset-0" />
      <div className="relative mx-auto max-w-[90rem] px-5 py-10 sm:px-8 sm:py-12 lg:py-14">
        <div className="grid items-end gap-8 lg:grid-cols-[minmax(0,0.85fr)_minmax(28rem,1.15fr)] lg:gap-14">
          <div>
            <p className="text-sm font-semibold text-[#B7FF3C]">Valuation workspace</p>
            <h1 className="valuator-display mt-3 max-w-[15ch] text-4xl font-semibold leading-[0.96] tracking-[-0.035em] text-[#F2F2EE] sm:text-5xl">
              Start a valuation.
            </h1>
          </div>
          <LandingSearch />
        </div>
        <div className="mt-10">
          <SavedStocksPanel />
        </div>
      </div>
    </section>
  )
}

function PublicHero() {
  const gridRef = useRef<HTMLDivElement>(null)
  const primaryLineRef = useRef<HTMLSpanElement>(null)
  const secondaryLineRef = useRef<HTMLSpanElement>(null)
  const supportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return

    const ease = "cubic-bezier(0.16, 1, 0.3, 1)"
    const animations = [
      gridRef.current?.animate(
        [
          { opacity: 0.14, clipPath: "inset(0 0 28% 0)" },
          { opacity: 0.35, clipPath: "inset(0 0 0% 0)" },
        ],
        { duration: 720, easing: ease },
      ),
      primaryLineRef.current?.animate(
        [
          { opacity: 0.62, transform: "translateY(18px)", clipPath: "inset(0 0 72% 0)" },
          { opacity: 1, transform: "translateY(0)", clipPath: "inset(0 0 0% 0)" },
        ],
        { duration: 620, delay: 70, easing: ease, fill: "backwards" },
      ),
      secondaryLineRef.current?.animate(
        [
          { opacity: 0.5, transform: "translateY(16px)", clipPath: "inset(0 0 76% 0)" },
          { opacity: 1, transform: "translateY(0)", clipPath: "inset(0 0 0% 0)" },
        ],
        { duration: 650, delay: 145, easing: ease, fill: "backwards" },
      ),
      supportRef.current?.animate(
        [
          { opacity: 0.68, transform: "translateX(14px)", filter: "blur(2px)" },
          { opacity: 1, transform: "translateX(0)", filter: "blur(0)" },
        ],
        { duration: 520, delay: 230, easing: ease, fill: "backwards" },
      ),
    ].filter(Boolean) as Animation[]

    return () => animations.forEach((animation) => animation.cancel())
  }, [])

  return (
    <section id="find-fair-value" className="valuator-hero relative min-h-[calc(100svh-4.5rem)] scroll-mt-24 border-b border-white/10">
      <div ref={gridRef} aria-hidden="true" className="valuator-coordinate-grid absolute inset-0" />
      <div className="relative mx-auto flex min-h-[calc(100svh-4.5rem)] max-w-[90rem] flex-col justify-between px-5 py-10 sm:px-8 sm:py-14 lg:py-16">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(21rem,0.75fr)] lg:items-start">
          <div>
            <p className="valuator-index mb-8 text-sm font-semibold text-[#B7FF3C]">VALUATION / EXPECTATIONS / EVIDENCE</p>
            <h1 className="valuator-display max-w-[13ch] text-balance text-[clamp(3.6rem,8.8vw,8.5rem)] font-semibold leading-[0.84] tracking-[-0.04em] text-[#F2F2EE]">
              <span ref={primaryLineRef} className="block">The market has a price.</span>
              <span ref={secondaryLineRef} className="mt-[0.08em] block text-[#8A8A83]">What does it assume?</span>
            </h1>
          </div>

          <div ref={supportRef} className="lg:pb-2">
            <p className="max-w-[32rem] text-pretty text-lg font-medium leading-8 text-[#D1D1CA]">
              VALUATOR reverse-engineers the expectations inside a stock price, then tests them against sourced evidence and five independent valuation methods.
            </p>
            <div className="mt-8"><LandingSearch /></div>
            <div className="mt-6"><SavedStocksPanel /></div>
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-6 border-t border-white/15 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-xl text-sm leading-6 text-[#A6A69F]">No ticker selected. No price, estimate, or fair value is shown until provider inputs are returned and validated.</p>
          <a href="#instrument" className="group inline-flex min-h-11 items-center gap-3 text-sm font-bold text-[#F2F2EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
            Enter the instrument <ArrowDownRight className="size-4 transition-transform duration-200 group-hover:translate-x-1 group-hover:translate-y-1" aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>
  )
}
