"use client"

import { Layers } from "lucide-react"
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"

/** Matches the actual FastAPI /api/v1/valuation/residual-income response. */
export interface RIData {
  ticker: string;
  computed_fair_value: number;
  margin_of_safety_percentage: number;
  valuation_status: string;
  underlying_assumptions: {
    roe: number;
    residual_incomes: number[];
    terminal_value: number;
    total_equity_value: number;
    bv_0: number;
    pv_future_wealth: number;
    book_value_per_share?: number | null;
    pv_future_wealth_per_share?: number | null;
    book_value_component_percentage?: number | null;
    future_wealth_component_percentage?: number | null;
    composition_available?: boolean;
    cost_of_equity?: number | null;
    computed_fair_value: number;
  };
  current_price: number;
}

export function RICard({ data }: { data: RIData }) {
  const total = data.computed_fair_value;
  const roe = data.underlying_assumptions.roe;
  const bookComponent = data.underlying_assumptions.book_value_per_share;
  const pvFutureWealth = data.underlying_assumptions.pv_future_wealth_per_share;
  const bookPct = data.underlying_assumptions.book_value_component_percentage;
  const wealthPct = data.underlying_assumptions.future_wealth_component_percentage;
  const costOfEquity = data.underlying_assumptions.cost_of_equity;
  const signedComponentsAvailable = (
    typeof bookComponent === "number"
    && Number.isFinite(bookComponent)
    && typeof pvFutureWealth === "number"
    && Number.isFinite(pvFutureWealth)
    && Number.isFinite(total)
  );
  const compositionAvailable = Boolean(
    data.underlying_assumptions.composition_available
    && typeof bookComponent === "number"
    && typeof pvFutureWealth === "number"
    && typeof bookPct === "number"
    && typeof wealthPct === "number"
  );

  const chartData = [
    { name: "Book Value", value: bookComponent, fill: "#8E8E99" },
    { name: "PV Future Wealth", value: pvFutureWealth, fill: "#C6F432" },
  ]

  const margin = data.margin_of_safety_percentage;

  return (
    <GlassCard>
      <CardHeading
        title="Residual Income Model (RI)"
        subtitle="Intrinsic value composition"
        icon={<Layers className="h-4 w-4" />}
        tooltipText="Calculates value based on the company's ability to generate returns (ROE) in excess of its cost of equity."
        badge={
          <span
            className={`rounded-md border px-2 py-1 font-mono text-xs tabular-nums ${
              margin >= 0
                ? "border-[#C6F432]/30 bg-[#C6F432]/10 text-[#C6F432]"
                : "border-amber-500/30 bg-amber-500/10 text-amber-400"
            }`}
          >
            IV ${fmt.money(total)} ({margin >= 0 ? "+" : ""}{margin.toFixed(1)}%)
          </span>
        }
      />
      {compositionAvailable ? <div className="flex items-center gap-4 p-5">
        <div className="relative h-36 w-36 shrink-0">
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} initialDimension={{ width: 144, height: 144 }}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey="value"
                innerRadius="66%"
                outerRadius="100%"
                paddingAngle={3}
                startAngle={90}
                endAngle={-270}
                stroke="none"
                isAnimationActive={false}
              >
                {chartData.map((d) => (
                  <Cell key={d.name} fill={d.fill} />
                ))}
              </Pie>
              <Tooltip
                formatter={(val) => [typeof val === "number" ? `$${fmt.money(val)}` : "N/A", ""]}
                contentStyle={{ backgroundColor: "#0B0B0C", borderColor: "#242429", color: "#FFFFFF" }}
                itemStyle={{ color: "#C6F432" }}
              />
            </PieChart>
          </ResponsiveContainer>
          
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center">
            <span className="text-xs text-[#8E8E99] font-medium">
              Intrinsic
            </span>
            <span className="text-base sm:text-lg font-mono font-bold tracking-tighter text-[#C6F432] mt-0.5">
              ${fmt.money(total)}
            </span>
          </div>
        </div>
        <div className="flex-1 space-y-4">
              <Legend
                color="bg-[#8E8E99]"
                label="Book Value"
                value={`$${fmt.money(bookComponent!)}`}
                pct={bookPct!}
              />
              <Legend
                color="bg-[#C6F432]"
                label="PV of Future Wealth"
                value={`$${fmt.money(pvFutureWealth!)}`}
                pct={wealthPct!}
              />
          <div className="flex items-center justify-between border-t border-[#242429] pt-3">
            <span className="text-xs text-[#8E8E99]">ROE</span>
            <span className="font-mono text-sm font-medium tabular-nums text-[#C6F432]">
              {fmt.pct(roe * 100)}
            </span>
          </div>
        </div>
      </div> : signedComponentsAvailable ? (
        <div className="p-5" data-testid="ri-signed-value-bridge">
          <div className="overflow-hidden rounded-md border border-[#242429] bg-[#0B0B0C]">
            <div className="border-b border-[#242429] px-4 py-3">
              <p className="text-sm font-semibold text-[#FFFFFF]">Signed value bridge</p>
              <p className="mt-1 text-xs leading-5 text-[#B8B8C2]">
                A negative future-wealth contribution reduces book value; it does not make the completed valuation unavailable.
              </p>
            </div>
            <div className="grid gap-px bg-[#242429] sm:grid-cols-3">
              <BridgeValue
                label="Book value / share"
                value={`$${fmt.money(bookComponent!)}`}
              />
              <BridgeValue
                label="PV future wealth / share"
                value={`${pvFutureWealth! < 0 ? "−" : "+"}$${fmt.money(Math.abs(pvFutureWealth!))}`}
                negative={pvFutureWealth! < 0}
              />
              <BridgeValue
                label="Intrinsic value / share"
                value={`$${fmt.money(total)}`}
                result
              />
            </div>
            <p className="border-t border-[#242429] px-4 py-3 text-center font-mono text-sm font-semibold tabular-nums text-[#FFFFFF]">
              ${fmt.money(bookComponent!)} {pvFutureWealth! < 0 ? "−" : "+"} ${fmt.money(Math.abs(pvFutureWealth!))} = ${fmt.money(total)}
            </p>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/20 bg-amber-500/[0.06] px-4 py-3 text-xs leading-5">
            <p className="text-amber-200/90">
              {typeof costOfEquity === "number" && Number.isFinite(costOfEquity) && roe < costOfEquity
                ? `Modeled ROE (${fmt.pct(roe * 100)}) is below Cost of Equity (${fmt.pct(costOfEquity * 100)}), creating negative residual income.`
                : "The discounted residual-income stream contributes negatively to current book value."}
            </p>
            <span className="font-mono tabular-nums text-[#FFFFFF]">ROE {fmt.pct(roe * 100)}</span>
          </div>
        </div>
      ) : <div className="p-5">
        <div className="rounded-md border border-[#242429] bg-[#0B0B0C] px-4 py-5">
          <p className="text-sm font-semibold text-[#FFFFFF]">Composition unavailable</p>
          <p className="mt-1 text-xs leading-5 text-[#8E8E99]">
            The response did not include finite book-value and future-wealth components. No composition was inferred.
          </p>
        </div>
      </div>}
    </GlassCard>
  )
}

function BridgeValue({
  label,
  value,
  negative = false,
  result = false,
}: {
  label: string
  value: string
  negative?: boolean
  result?: boolean
}) {
  return (
    <div className="flex min-h-20 flex-col justify-center bg-[#0B0B0C] px-4 py-3">
      <span className="text-[11px] text-[#8E8E99]">{label}</span>
      <span className={`mt-1 font-mono text-base font-semibold tabular-nums ${
        negative ? "text-amber-300" : result ? "text-[#C6F432]" : "text-[#FFFFFF]"
      }`}>
        {value}
      </span>
    </div>
  )
}

function Legend({
  color,
  label,
  value,
  pct,
}: {
  color: string
  label: string
  value: string
  pct: number
}) {
  const safePct = isNaN(pct) ? 0 : pct;
  const barPct = Math.max(0, Math.min(100, safePct));
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-sm ${color}`} />
          <span className="text-xs text-[#8E8E99]">{label}</span>
        </div>
        <span className="font-mono text-sm font-medium tabular-nums text-[#FFFFFF]">{value}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-2 pl-4.5">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-[#242429]">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${barPct}%` }} />
        </div>
        <span className="font-mono text-[11px] tabular-nums text-[#8E8E99]">{safePct.toFixed(0)}%</span>
      </div>
    </div>
  )
}
