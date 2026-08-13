export type Scenario = "bear" | "base" | "bull"

export const scenarioMeta: Record<
  Scenario,
  { label: string; classes: string }
> = {
  bear: {
    label: "Bear Case",
    classes: "bg-amber-500/10 text-amber-400 border-amber-500/30 shadow-[0_0_16px_-4px_rgba(245,158,11,0.5)]",
  },
  base: {
    label: "Base Case",
    classes: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_16px_-4px_rgba(16,185,129,0.5)]",
  },
  bull: {
    label: "Bull Case",
    classes: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30 shadow-[0_0_16px_-4px_rgba(34,211,238,0.5)]",
  },
}

export const fmt = {
  money: (n: number, d = 2) =>
    (n ?? 0).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (n: number, d = 1) => `${(n ?? 0) >= 0 ? "" : ""}${(n ?? 0).toFixed(d)}%`,
  bn: (n: number, d = 1) => `$${(n ?? 0).toFixed(d)}B`,
}
