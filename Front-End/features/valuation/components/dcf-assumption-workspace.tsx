"use client"

import { useMemo, useState } from "react"
import { ChevronDown, RotateCcw, SlidersHorizontal } from "lucide-react"
import type { DcfAssumptionValues } from "@/features/valuation-assumptions/types"
import { validateDcfAssumptionValues } from "@/features/valuation-assumptions/validation"
import type { DCFData } from "./DCFCard"
import { isRegulatoryFcfe } from "./DCFCard"

export type { DcfAssumptionValues } from "@/features/valuation-assumptions/types"

export function assumptionsFromResponse(data?: DCFData): DcfAssumptionValues | null {
  if (!data || data.valuation_status !== "CALCULATED") return null
  const assumptions = data.underlying_assumptions
  const growthRate = assumptions.stage_1_growth_rate
  const perpetualGrowthRate = assumptions.perpetual_growth_rate
  const discountRate =
    assumptions.discount_rate ?? assumptions.wacc ?? assumptions.cost_of_equity
  if (
    typeof growthRate !== "number" ||
    typeof perpetualGrowthRate !== "number" ||
    typeof discountRate !== "number"
  ) {
    return null
  }
  return {
    growthRate: growthRate * 100,
    perpetualGrowthRate: perpetualGrowthRate * 100,
    discountRate: discountRate * 100,
  }
}

type FieldKey = keyof DcfAssumptionValues
type FieldText = Record<FieldKey, string>

function toFieldText(values: DcfAssumptionValues): FieldText {
  return {
    growthRate: String(Number(values.growthRate.toFixed(2))),
    perpetualGrowthRate: String(Number(values.perpetualGrowthRate.toFixed(2))),
    discountRate: String(Number(values.discountRate.toFixed(2))),
  }
}

function parseFields(fields: FieldText): DcfAssumptionValues | null {
  if (Object.values(fields).some((value) => value.trim() === "")) return null
  const parsed = {
    growthRate: Number(fields.growthRate),
    perpetualGrowthRate: Number(fields.perpetualGrowthRate),
    discountRate: Number(fields.discountRate),
  }
  return Object.values(parsed).every(Number.isFinite) ? parsed : null
}

function sameEditableAssumptions(left: DcfAssumptionValues, right: DcfAssumptionValues) {
  const leftFields = toFieldText(left)
  const rightFields = toFieldText(right)
  return (Object.keys(leftFields) as FieldKey[]).every(
    (key) => leftFields[key] === rightFields[key],
  )
}

export function DcfAssumptionWorkspace({
  ticker,
  methodologyData,
  base,
  applied,
  isUpdating,
  isResetting,
  requestError,
  persistenceLabel,
  persistenceError,
  onApply,
  onReset,
  onRetryModel,
  onRetryPersistence,
}: {
  ticker: string
  methodologyData?: DCFData
  base: DcfAssumptionValues | null
  applied: DcfAssumptionValues | null
  isUpdating: boolean
  isResetting: boolean
  requestError?: Error
  persistenceLabel: string | null
  persistenceError: string | null
  onApply: (next: DcfAssumptionValues) => void
  onReset: () => void
  onRetryModel: () => void
  onRetryPersistence: () => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const source = applied ?? base
  const sourceKey = source
    ? `${ticker}:${source.growthRate}:${source.perpetualGrowthRate}:${source.discountRate}`
    : ticker
  const [draftState, setDraftState] = useState<{ key: string; fields: FieldText }>(() => ({
    key: sourceKey,
    fields: toFieldText(source ?? { growthRate: 0, perpetualGrowthRate: 2, discountRate: 10 }),
  }))
  const fieldText = draftState.key === sourceKey
    ? draftState.fields
    : toFieldText(source ?? { growthRate: 0, perpetualGrowthRate: 2, discountRate: 10 })

  const parsed = useMemo(() => parseFields(fieldText), [fieldText])
  if (!base || !source) return null

  const valid = parsed !== null && validateDcfAssumptionValues(parsed)
  const dirty = parsed === null || !sameEditableAssumptions(parsed, applied ?? base)
  const modified = applied !== null
  const retryingModel = Boolean(requestError && !dirty)
  const stateLabel = isResetting
      ? "Resetting saved assumptions"
      : isUpdating
        ? "Updating model"
        : dirty
          ? "Draft not applied"
          : requestError
            ? "Last complete result retained"
            : persistenceLabel ?? (modified ? "User modified" : "Model defaults")

  const fields: Array<{
    key: FieldKey
    label: string
    min: number
    max?: number
    rangeHelp: string
  }> = [
    { key: "growthRate", label: "Stage 1 growth", min: 0, rangeHelp: "Required · ≥ 0%" },
    { key: "perpetualGrowthRate", label: "Perpetual growth", min: 1, max: 4, rangeHelp: "Required · 1–4%" },
    {
      key: "discountRate",
      label: isRegulatoryFcfe(methodologyData) ? "Discount rate (Ke)" : "Discount rate (WACC)",
      min: 5,
      max: 15,
      rangeHelp: "Required · 5–15% · must exceed perpetual growth",
    },
  ]

  const fieldError = (field: (typeof fields)[number]) => {
    const text = fieldText[field.key].trim()
    if (!text) return `${field.label} is required.`
    const value = Number(text)
    if (!Number.isFinite(value)) return `Enter a valid number for ${field.label.toLowerCase()}.`
    if (value < field.min || (field.max !== undefined && value > field.max)) {
      if (field.max !== undefined) {
        return `${field.label} must be between ${field.min}% and ${field.max}%.`
      }
      return `${field.label} must be at least ${field.min}%.`
    }
    if (
      field.key === "discountRate" &&
      parsed &&
      parsed.discountRate <= parsed.perpetualGrowthRate
    ) {
      return "Discount rate must be greater than perpetual growth."
    }
    return null
  }

  const summary = parsed && valid
    ? `${parsed.growthRate.toFixed(1)}% stage growth · ${parsed.perpetualGrowthRate.toFixed(1)}% perpetual · ${parsed.discountRate.toFixed(1)}% discount rate`
    : "Review the required assumptions before applying"

  return (
    <section
      aria-label="DCF assumption workspace"
      aria-busy={isUpdating || isResetting}
      className="mb-6 rounded-md border border-[#1A2E20] bg-[#111613]"
    >
      <div className={`flex flex-wrap items-center justify-between gap-3 px-4 py-2 ${isOpen ? "border-b border-[#1A2E20]" : ""}`}>
        <button
          type="button"
          aria-expanded={isOpen}
          aria-controls="dcf-assumption-fields"
          onClick={() => setIsOpen((current) => !current)}
          className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]"
        >
          <SlidersHorizontal className="h-4 w-4 text-[#B7FF3C]" aria-hidden="true" />
          <div className="min-w-0">
            <span className="block text-sm font-semibold text-[#E0E6E2]">DCF assumptions</span>
            <p className="mt-0.5 truncate text-xs text-[#869E8F]">{summary}</p>
          </div>
          <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-[#869E8F] transition-transform ${isOpen ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>
        <div className="flex items-center gap-2">
          <span className={`rounded-full border px-2 py-1 text-[11px] font-medium ${dirty || modified ? "border-amber-500/30 bg-amber-500/10 text-amber-300" : "border-[#1A2E20] bg-[#0A0D0B] text-[#9AB0A1]"}`}>
            {dirty || modified ? "User assumption" : "Model input"}
          </span>
          <span role="status" className="text-xs text-[#9AB0A1]">{stateLabel}</span>
        </div>
      </div>

      {isOpen ? <div id="dcf-assumption-fields" className="grid gap-4 p-4 lg:grid-cols-[repeat(3,minmax(0,1fr))_auto] lg:items-start">
        {fields.map((field) => {
          const error = fieldError(field)
          const changed = parsed
            ? toFieldText(parsed)[field.key] !== toFieldText(base)[field.key]
            : fieldText[field.key] !== toFieldText(base)[field.key]
          const descriptionId = `dcf-${field.key}-description`
          return (
            <label key={field.key} className="block text-xs text-[#9AB0A1]">
              <span className="flex items-center justify-between gap-2">
                {field.label}
                {changed ? (
                  <span className="font-mono text-[11px] text-amber-300">
                    Base {base[field.key].toFixed(1)}%
                  </span>
                ) : null}
              </span>
              <div className="relative mt-2">
                <input
                  type="number"
                  inputMode="decimal"
                  aria-label={field.label}
                  aria-invalid={Boolean(error)}
                  aria-describedby={descriptionId}
                  min={field.min}
                  max={field.max}
                  step="0.1"
                  value={fieldText[field.key]}
                  onChange={(event) => setDraftState((current) => ({
                    key: sourceKey,
                    fields: {
                      ...(current.key === sourceKey ? current.fields : fieldText),
                      [field.key]: event.target.value,
                    },
                  }))}
                  className={`h-11 w-full rounded-sm border bg-[#0A0D0B] px-3 pr-8 font-mono text-sm tabular-nums text-[#E0E6E2] outline-none focus:ring-1 ${error ? "border-amber-500/60 focus:border-amber-400 focus:ring-amber-400/30" : "border-[#294231] focus:border-[#B7FF3C] focus:ring-[#B7FF3C]/40"}`}
                />
                <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center font-mono text-xs text-[#869E8F]">%</span>
              </div>
              <span id={descriptionId} className={`mt-1.5 block min-h-4 text-[11px] leading-4 ${error ? "text-amber-300" : "text-[#869E8F]"}`}>
                {error ?? field.rangeHelp}
              </span>
            </label>
          )
        })}

        <div className="flex flex-wrap gap-2 lg:justify-end lg:pt-6">
          <button
            type="button"
            onClick={() => {
              if (retryingModel) onRetryModel()
              else if (parsed) onApply(parsed)
            }}
            disabled={(!dirty && !retryingModel) || !valid || isUpdating || isResetting}
            className="h-11 rounded-sm bg-[#B7FF3C] px-4 text-sm font-semibold text-[#071008] transition-colors hover:bg-[#C7FF69] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isUpdating ? "Applying…" : retryingModel ? "Retry model" : "Apply to workspace"}
          </button>
          <button
            type="button"
            onClick={() => {
              setDraftState({ key: sourceKey, fields: toFieldText(base) })
              onReset()
            }}
            disabled={(!modified && !dirty) || isResetting}
            className="inline-flex h-11 items-center gap-2 rounded-sm border border-[#294231] px-3 text-sm font-medium text-[#C8D4CC] hover:bg-[#1A2E20] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            {isResetting ? "Resetting…" : "Reset all"}
          </button>
        </div>
      </div> : null}

      {isOpen && requestError && !isUpdating ? (
        <div role="status" className="border-t border-[#1A2E20] px-4 py-3 text-xs leading-5 text-[#A9BAAF]">
          <span className="font-semibold text-[#DCEBE2]">Model update unavailable. </span>
          The last complete result remains visible. {requestError.message}
        </div>
      ) : null}
      {isOpen && persistenceError ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 border-t border-[#1A2E20] px-4 py-3 text-xs leading-5 text-[#FFB4A9]">
          <span><strong className="text-[#FFD0C8]">Assumptions weren’t synced. </strong>{persistenceError}</span>
          <button type="button" onClick={onRetryPersistence} className="min-h-11 rounded-sm border border-[#6B3A3E] px-3 font-semibold text-[#FFD0C8] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C]">
            Retry sync
          </button>
        </div>
      ) : null}
    </section>
  )
}
