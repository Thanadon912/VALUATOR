"use client"

import { AnimatePresence, motion } from "framer-motion"
import { CircleDot, Cpu, FlaskConical, Landmark, Waves } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"
import type { DCFData } from "./DCFCard"
import { methodologyBadgeClasses } from "./DCFCard"

type TelemetryMetric = {
  icon: typeof FlaskConical
  label: string
  value: string
  tint: string
}

function money(value?: number | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return fmt.bn(value / 1e9, 1)
}

function pct(value?: number | null, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return `${(value * 100).toFixed(digits)}%`
}

function getHorizonYears(data?: DCFData): number {
  const metadata = data?.engine_metadata ?? data?.underlying_assumptions?.engine_metadata ?? {}
  if (typeof metadata.projection_years === 'number') {
    return metadata.projection_years
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const forwardDcfProjections = (data as any)?.forward_dcf?.scenarios?.base?.projections;
  if (forwardDcfProjections && Array.isArray(forwardDcfProjections)) {
    return forwardDcfProjections.length;
  }
  if (data?.projections && Array.isArray(data.projections) && data.projections.length > 0) {
    return data.projections.length;
  }
  return 7;
}

function buildMetrics(data?: DCFData): TelemetryMetric[] {
  const metadata = data?.engine_metadata ?? data?.underlying_assumptions?.engine_metadata ?? {}
  const horizonYears = getHorizonYears(data)
  
  switch (data?.valuation_methodology) {
    case "Capitalized R&D DCF":
      return [
        {
          icon: FlaskConical,
          label: "Capitalized R&D Asset",
          value: money(metadata.capitalized_rnd_asset),
          tint: "text-[#C6F432]",
        },
        {
          icon: CircleDot,
          label: "Explicit Modeling Horizon",
          value: `${horizonYears}-Year Base + TV`,
          tint: "text-[#C6F432]",
        },
      ]
    case "Regulatory FCFE":
      return [
        {
          icon: Landmark,
          label: "Tier 1 Capital Ratio Used",
          value: pct(metadata.tier_1_capital_ratio_used),
          tint: "text-[#C6F432]",
        },
        {
          icon: CircleDot,
          label: "Projected Loan Growth",
          value: pct(metadata.projected_loan_growth),
          tint: "text-[#C6F432]",
        },
        {
          icon: CircleDot,
          label: "Discount Rate Type",
          value: metadata.discount_rate_type ?? "Cost of Equity (Ke)",
          tint: "text-[#C6F432]",
        },
      ]
    case "Normalized Median DCF":
      return [
        {
          icon: Waves,
          label: "10-Year Historical Median Margin",
          value: pct(metadata["10_year_historical_median_margin"]),
          tint: "text-[#FFFFFF]",
        },
        {
          icon: CircleDot,
          label: "Normalized Base EBIT Generated",
          value: money(metadata.normalized_base_ebit_generated),
          tint: "text-[#FFFFFF]",
        },
      ]
    case "SOTP Reverse DCF": {
      const sotp = data?.reverse_dcf_sotp
      const reverseHorizonYears = (sotp && 'horizon_years' in sotp) ? Number(sotp.horizon_years) : 0
      return [
        {
          icon: FlaskConical,
          label: "Capitalized R&D Asset",
          value: money(metadata.capitalized_rnd_asset),
          tint: "text-[#C6F432]",
        },
        {
          icon: CircleDot,
          label: "Explicit Modeling Horizon",
          value: reverseHorizonYears > 0 ? `${reverseHorizonYears} Yrs (SOTP + Real Options)` : "SOTP + Real Options",
          tint: "text-[#C6F432]",
        },
      ]
    }
    case "Standard Driver-Based DCF":
    default:
      return [
        {
          icon: CircleDot,
          label: "Adjustment Applied",
          value: metadata.fallback_reason ?? "None - standard driver model",
          tint: "text-[#C6F432]",
        },
        {
          icon: CircleDot,
          label: "Projection Basis",
          value: `${horizonYears}-year driver-based matrix`,
          tint: "text-[#C6F432]",
        },
      ]
  }
}

export function EngineTelemetry({ data }: { data?: DCFData }) {
  const methodology = data?.valuation_methodology ?? "Adaptive Valuation Engine"
  const metrics = buildMetrics(data)

  return (
    <GlassCard>
      <CardHeading
        title="Engine Telemetry"
        subtitle="Live metadata emitted by the adaptive routing engine"
        icon={<Cpu className="h-4 w-4" />}
        tooltipText="Displays the specific valuation model selected by the adaptive routing engine based on the company's business structure."
        badge={
          <span className={`rounded-full px-3 py-1 text-xs font-mono ${methodologyBadgeClasses(methodology)}`}>
            {methodology}
          </span>
        }
      />
      <div className="p-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={methodology}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.28, ease: "easeOut" }}
            className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
          >
            {metrics.map((metric) => {
              const Icon = metric.icon
              return (
                <div
                  key={metric.label}
                  className="flex items-start gap-3 rounded-md border border-[#242429] bg-[#0B0B0C] p-4"
                >
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#323238] bg-[#121214]">
                    <Icon className={`h-4 w-4 ${metric.tint}`} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs text-[#8E8E99]">{metric.label}</p>
                    <p className={`mt-1 font-mono text-sm font-semibold tabular-nums ${metric.tint}`}>
                      {metric.value}
                    </p>
                  </div>
                </div>
              )
            })}
          </motion.div>
        </AnimatePresence>
      </div>
    </GlassCard>
  )
}
