import { Scale } from "lucide-react"
import { fmt } from "@/lib/valuation"

export type ValuationComparisonItem = {
  id: string
  method: string
  methodology?: string | null
  status?: string
  fairValue?: number | null
  marginOfSafety?: number | null
  hasMaterialSensitivity?: boolean
  isLoading?: boolean
  hasError?: boolean
}

function statusMeta(item: ValuationComparisonItem) {
  if (item.hasError) return { label: "Error", classes: "border-red-500/30 bg-red-500/10 text-red-300" }
  if (item.isLoading && !item.status) return { label: "Loading", classes: "border-[#323238] bg-[#0B0B0C] text-[#B8B8C2]" }
  if (
    item.hasMaterialSensitivity &&
    (item.status === "CALCULATED" || item.status === "APPLICABLE")
  ) {
    return {
      label: "Available · High sensitivity",
      classes: "border-amber-500/30 bg-amber-500/10 text-amber-200",
    }
  }
  switch (item.status) {
    case "CALCULATED":
    case "APPLICABLE":
      return { label: "Available", classes: "border-[#C6F432]/30 bg-[#C6F432]/10 text-[#C6F432]" }
    case "INAPPLICABLE":
      return { label: "Not applicable", classes: "border-[#323238] bg-[#0B0B0C] text-[#B8B8C2]" }
    case "MISSING_INPUT":
      return { label: "Missing inputs", classes: "border-amber-500/30 bg-amber-500/10 text-amber-300" }
    case "INVALID_INPUT":
      return { label: "Invalid inputs", classes: "border-red-500/30 bg-red-500/10 text-red-300" }
    default:
      return { label: item.isLoading ? "Loading" : "Unavailable", classes: "border-[#323238] bg-[#0B0B0C] text-[#B8B8C2]" }
  }
}

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

export function ValuationComparison({
  items,
  marketPrice,
}: {
  items: ValuationComparisonItem[]
  marketPrice: number | null
}) {
  return (
    <section aria-labelledby="valuation-comparison-title" className="rounded-md border border-[#242429] bg-[#121214]">
      <div className="flex flex-col gap-2 border-b border-[#242429] px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-[#242429] bg-[#0B0B0C] text-[#C6F432]">
            <Scale className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <h2 id="valuation-comparison-title" className="text-sm font-semibold text-[#FFFFFF]">Compare valuation methods</h2>
            <p className="mt-0.5 text-xs leading-5 text-[#8E8E99]">Each result remains independent; no consensus value is inferred.</p>
          </div>
        </div>
        <div className="text-left sm:text-right">
          <p className="text-[11px] uppercase tracking-[0.12em] text-[#8E8E99]">Market reference</p>
          <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-[#FFFFFF]">
            {finite(marketPrice) ? `$${fmt.money(marketPrice)}` : "Unavailable"}
          </p>
        </div>
      </div>

      <div className="hidden grid-cols-[minmax(0,1.5fr)_minmax(7rem,0.7fr)_minmax(7rem,0.7fr)_minmax(8rem,0.8fr)] gap-3 border-b border-[#242429] px-5 py-2 text-[10px] uppercase tracking-[0.12em] text-[#8E8E99] md:grid">
        <span>Method</span><span>Status</span><span>Fair value</span><span>Margin vs market</span>
      </div>
      <div className="divide-y divide-[#242429]">
        {items.map((item) => {
          const state = statusMeta(item)
          // APPLICABLE is accepted for compatibility with API responses from
          // older deployments; current endpoints normalize success to CALCULATED.
          const calculated = item.status === "CALCULATED" || item.status === "APPLICABLE"
          return (
            <div key={item.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1.5fr)_minmax(7rem,0.7fr)_minmax(7rem,0.7fr)_minmax(8rem,0.8fr)] md:items-center">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[#FFFFFF]">{item.method}</p>
                <p className="mt-1 truncate text-xs text-[#8E8E99]">
                  {item.hasMaterialSensitivity
                    ? `${item.methodology || "Independent valuation engine"} · Full-consensus result`
                    : item.methodology || "Independent valuation engine"}
                </p>
              </div>
              <div>
                <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-medium ${state.classes}`}>{state.label}</span>
              </div>
              <div className="grid grid-cols-2 gap-3 md:contents">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.1em] text-[#8E8E99] md:hidden">Fair value</p>
                  <p className="mt-1 font-mono text-sm font-semibold tabular-nums text-[#FFFFFF] md:mt-0">
                    {calculated && finite(item.fairValue) ? `$${fmt.money(item.fairValue)}` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.1em] text-[#8E8E99] md:hidden">Margin vs market</p>
                  <p className={`mt-1 font-mono text-sm font-semibold tabular-nums md:mt-0 ${finite(item.marginOfSafety) && item.marginOfSafety < 0 ? "text-amber-300" : "text-[#FFFFFF]"}`}>
                    {calculated && finite(item.marginOfSafety) ? `${item.marginOfSafety > 0 ? "+" : ""}${fmt.pct(item.marginOfSafety)}` : "—"}
                  </p>
                </div>
              </div>
              <span className="sr-only">{calculated ? "Derived output from the active model inputs." : "No derived output is available."}</span>
            </div>
          )
        })}
      </div>
      <p className="border-t border-[#242429] px-5 py-3 text-[11px] text-[#8E8E99]">Values marked available are derived outputs, not provider forecasts.</p>
    </section>
  )
}
