"use client"

import { Layers } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"

type EvidenceSegment = {
  name?: string;
  reported_revenue?: number | null;
  revenue_percentage?: number | null;
  currency?: string | null;
  period_end?: string | null;
  source?: string | null;
  filing_url?: string | null;
};

export type SotpBreakdown = {
  status?: string;
  classification_profile?: string;
  segment_source?: string;
  segments?: EvidenceSegment[];
  warning?: string;
};

// Segment revenue is filing-backed, but a segment margin, reinvestment rate,
// and discount rate are required to turn revenue into a segment valuation
// (docs/valuation-calculations.md §7). Without them this shows reported revenue mix as
// evidence only rather than fabricating a "Core Business = 100% EV" segment
// value.
export function SotpEvidenceNote({ data }: { data?: SotpBreakdown | null }) {
  if (!data || (data.status !== "EVIDENCE_ONLY" && data.status !== "UNAVAILABLE")) return null;

  const segments = data.segments ?? [];

  return (
    <GlassCard>
      <CardHeading
        title="Segment Valuation"
        subtitle="Sum-of-the-parts is not calculated for this company"
        icon={<Layers className="h-4 w-4" />}
        tooltipText="Reported segment revenue alone is not sufficient for a segment valuation. Segment margins, reinvestment, and a segment-specific discount rate are also required."
        badge={
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] font-semibold text-amber-300">
            {data.status === "EVIDENCE_ONLY" ? "Evidence Only" : "Unavailable"}
          </span>
        }
      />
      <div className="flex flex-col gap-4 p-5">
        {data.warning ? (
          <p className="text-sm leading-relaxed text-[#869E8F]">{data.warning}</p>
        ) : null}
        {segments.length > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {segments.map((segment, index) => (
              <div
                key={`${segment.name ?? "segment"}-${index}`}
                className="rounded-md border border-[#1A2E20] bg-[#0A0D0B]/40 p-3"
              >
                <p className="text-xs font-semibold text-[#E0E6E2]">{segment.name ?? "Segment"}</p>
                <p className="mt-1 font-mono text-sm tabular-nums text-[#869E8F]">
                  {typeof segment.revenue_percentage === "number"
                    ? `${fmt.pct(segment.revenue_percentage, 1)} of revenue`
                    : "Revenue share unavailable"}
                  {typeof segment.reported_revenue === "number"
                    ? ` · ${segment.currency ?? "$"}${fmt.money(segment.reported_revenue / 1e9, 2)}B`
                    : ""}
                </p>
                {segment.period_end ? (
                  <p className="mt-1 text-[10px] text-[#5C6B62]">As of {segment.period_end}</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </GlassCard>
  )
}
