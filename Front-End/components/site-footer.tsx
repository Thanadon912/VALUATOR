import Link from "next/link"

export function SiteFooter() {
  return (
    <footer className="bg-[#B7FF3C] text-[#050505]">
      <div className="mx-auto max-w-[90rem] px-5 py-12 sm:px-8">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Link href="/" className="valuator-wordmark inline-flex min-h-11 items-center text-4xl font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#050505]">VALUATOR<span aria-hidden="true" className="ml-2 inline-block size-3 bg-[#050505]" /></Link>
            <p className="mt-4 max-w-xl text-base font-medium leading-7">Market expectations, made visible through sourced evidence and explicit assumptions.</p>
          </div>
          <a href="#find-fair-value" className="valuator-display inline-flex min-h-12 items-center border-b-2 border-[#050505] text-2xl font-semibold">Value a ticker ↗</a>
        </div>
        <div className="mt-14 flex flex-col gap-5 border-t border-[#050505]/30 pt-6 text-sm font-medium lg:flex-row lg:items-start lg:justify-between">
          <p className="max-w-4xl">For informational research only—not investment advice. Model outputs depend on provider availability and explicit assumptions. Inspect the reported inputs, warnings, methodology, and source references before making a decision.</p>
          <p className="shrink-0">© {new Date().getFullYear()} VALUATOR</p>
        </div>
      </div>
    </footer>
  )
}
