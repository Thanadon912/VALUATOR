import { Navbar } from "@/components/navbar"
import { Hero } from "@/components/hero"
import { MarketExpectationsInstrument } from "@/components/market-expectations-instrument"
import { SiteFooter } from "@/components/site-footer"

export default function Page() {
  return (
    <div className="valuator-site min-h-screen overflow-x-clip bg-[#0B0B0C] text-[#FFFFFF]">
      <a href="#main-content" className="sr-only z-[60] bg-[#C6F432] px-4 py-3 font-semibold text-[#0B0B0C] focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Skip to main content</a>
      <Navbar />
      <main id="main-content">
        <Hero />
        <MarketExpectationsInstrument />
      </main>
      <SiteFooter />
    </div>
  )
}
