import type React from "react"
import { cn } from "@/lib/utils"
import { InfoTooltip } from "./info-tooltip"

export function GlassCard({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md border border-[#1A2E20] bg-[#111613]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeading({
  title,
  subtitle,
  icon,
  badge,
  tooltipText,
}: {
  title: string | React.ReactNode
  subtitle?: string
  icon?: React.ReactNode
  badge?: React.ReactNode
  tooltipText?: string
}) {
  return (
    <div className="flex flex-col items-stretch justify-between gap-4 border-b border-[#1A2E20] px-5 py-4 sm:flex-row sm:items-start">
      <div className="flex min-w-0 items-center gap-3">
        {icon ? (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-[#1A2E20] bg-[#0A0D0B] text-emerald-400">
            {icon}
          </div>
        ) : null}
        <div className="min-w-0">
          <h3 className="flex items-center text-sm font-semibold tracking-tight text-[#E0E6E2]">
            {title}
            {tooltipText && <InfoTooltip text={tooltipText} />}
          </h3>
          {subtitle ? (
            <p className="mt-0.5 text-xs text-[#869E8F]">{subtitle}</p>
          ) : null}
        </div>
      </div>
      {badge ? <div className="self-start">{badge}</div> : null}
    </div>
  )
}
