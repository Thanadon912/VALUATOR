import { Navbar } from "@/components/navbar"
import { Hero } from "@/components/hero"
import { MarketExpectationsInstrument } from "@/components/market-expectations-instrument"
import { SiteFooter } from "@/components/site-footer"

export default function Page() {
  return (
    <div className="valuator-site min-h-screen overflow-x-clip bg-[#050505] text-[#F2F2EE]">
      <a href="#main-content" className="sr-only z-[60] bg-[#B7FF3C] px-4 py-3 font-semibold text-[#050505] focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Skip to main content</a>
      <Navbar />
      <main id="main-content">
        <Hero />
        <MarketExpectationsInstrument />
      </main>
      <SiteFooter />
    </div>
  )
}
