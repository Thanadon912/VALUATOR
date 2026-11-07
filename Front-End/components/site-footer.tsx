import Link from "next/link"

export function SiteFooter() {
  return (
    <footer className="border-t border-white/12 bg-[#0B0B0C] text-[#FFFFFF]">
      <div className="mx-auto max-w-[90rem] px-5 py-12 sm:px-8">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Link href="/" className="valuator-wordmark inline-flex min-h-11 items-center text-4xl font-bold text-[#FFFFFF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432]">VALUATOR<span aria-hidden="true" className="ml-2 inline-block size-3 bg-[#C6F432]" /></Link>
            <p className="mt-4 max-w-xl text-base font-medium leading-7 text-[#B8B8C2]">Market expectations, made visible through sourced evidence and explicit assumptions.</p>
          </div>
          <a href="#find-fair-value" className="valuator-display inline-flex min-h-12 items-center border-b-2 border-[#C6F432] text-2xl font-semibold text-[#C6F432] transition-colors hover:border-[#D4F759] hover:text-[#D4F759] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#C6F432]">Value a ticker ↗</a>
        </div>
        <div className="mt-14 flex flex-col gap-5 border-t border-white/12 pt-6 text-sm font-medium text-[#8E8E99] lg:flex-row lg:items-start lg:justify-between">
          <p className="max-w-4xl">For informational research only—not investment advice. Model outputs depend on provider availability and explicit assumptions. Inspect the reported inputs, warnings, methodology, and source references before making a decision.</p>
          <p className="shrink-0 text-[#B8B8C2]">© {new Date().getFullYear()} VALUATOR</p>
        </div>
      </div>
    </footer>
  )
}
