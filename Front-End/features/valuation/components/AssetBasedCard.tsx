"use client"

import { useState } from "react"
import { Landmark } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"

/** Matches the actual FastAPI /api/v1/valuation/asset-based response. */
export interface AssetBasedData {
  ticker: string;
  computed_fair_value: number;
  margin_of_safety_percentage: number;
  valuation_status: string;
  underlying_assumptions: {
    total_assets: number;
    total_liabilities: number;
    goodwill: number;
    intangible_assets: number;
    nav: number;
    tangible_nav: number;
    standard_nav_per_share: number;
    tangible_net_net_per_share: number;
    computed_fair_value: number;
    scenario_margin_of_safety_percentage?: {
      standard_nav?: number | null;
      tangible_nav?: number | null;
    };
    scenario_margin_of_safety_basis?: string;
  };
  current_price: number;
}

export function AssetBasedCard({ data }: { data: AssetBasedData }) {
  const [tangible, setTangible] = useState(false)
  const ua = data.underlying_assumptions;

  const nav = tangible
    ? ua.tangible_net_net_per_share
    : ua.standard_nav_per_share;

  const equity = tangible ? ua.tangible_nav : ua.nav;
  const margin = tangible
    ? ua.scenario_margin_of_safety_percentage?.tangible_nav
    : ua.scenario_margin_of_safety_percentage?.standard_nav;

  const bn = (num: number | null | undefined) =>
    typeof num === "number" && Number.isFinite(num) ? `$${(num / 1e9).toFixed(2)}B` : "N/A";
  const money = (num: number | null | undefined) =>
    typeof num === "number" && Number.isFinite(num) ? `$${num.toFixed(2)}` : "N/A";

  return (
    <GlassCard>
      <CardHeading
        title="Asset-Based Valuation"
        subtitle="Net asset value from the balance sheet"
        icon={<Landmark className="h-4 w-4" />}
        tooltipText="Estimates the floor value of the company based on its balance sheet (Assets minus Liabilities), representing the tangible book value."
        badge={
          <div className="flex rounded-lg border border-[#1A2E20] bg-[#111613] p-0.5">
            <button
              type="button"
              onClick={() => setTangible(false)}
              aria-pressed={!tangible}
              className={`min-h-11 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                !tangible ? "bg-[#1A2E20] text-white shadow" : "text-[#88998C] hover:text-white"
              }`}
            >
              Book Value
            </button>
            <button
              type="button"
              onClick={() => setTangible(true)}
              aria-pressed={tangible}
              className={`min-h-11 rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                tangible ? "bg-[#1A2E20] text-white shadow" : "text-[#88998C] hover:text-white"
              }`}
            >
              Tangible Net-Net
            </button>
          </div>
        }
      />
      <div className="p-5">
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-[#1A2E20] bg-[#1A2E20] sm:grid-cols-3">
          <BalanceMetric label="Total Assets" value={bn(ua.total_assets)} />
          <BalanceMetric label="Total Liabilities" value={bn(ua.total_liabilities)} />
          <BalanceMetric label={tangible ? "Tangible NAV" : "Standard NAV"} value={bn(equity)} accent />
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3">
          <div className="rounded-md border border-[#1A2E20] bg-[#111613] p-3">
            <p className="text-xs text-[#88998C]">NAV / Share</p>
            <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-white">
              {money(nav)}
            </p>
          </div>
          <div className="flex flex-col justify-between rounded-md border border-[#1A2E20] bg-[#111613] p-3">
            <p className="text-xs text-[#88998C]">Margin of Safety</p>
            {typeof margin === "number" && Number.isFinite(margin) ? <span
              className={`mt-1 inline-flex w-fit items-center rounded-md px-2 py-1 font-mono text-sm font-semibold tabular-nums ${
                margin >= 0
                  ? "border border-[#00FF66]/30 bg-[#00FF66]/10 text-[#00FF66]"
                  : "border border-amber-500/30 bg-amber-500/10 text-amber-400"
              }`}
            >
              {margin >= 0 ? "+" : ""}
              {margin.toFixed(1)}%
            </span> : <span className="mt-1 font-mono text-sm text-[#88998C]">Unavailable</span>}
          </div>
        </div>
      </div>
    </GlassCard>
  )
}

function BalanceMetric({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-[#090A0B] p-3">
      <p className="text-xs text-[#88998C]">{label}</p>
      <p className={`mt-1 font-mono text-sm font-semibold tabular-nums ${accent ? "text-[#00FF66]" : "text-white"}`}>
        {value}
      </p>
    </div>
  )
}
