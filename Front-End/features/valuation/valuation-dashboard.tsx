"use client"

import { useState, useEffect, useMemo, useRef, useCallback } from "react"
import type { ReactNode } from "react"
import { motion, AnimatePresence, useReducedMotion } from "framer-motion"
import useSWR from "swr"
import { Activity, CircleAlert, CircleOff, Database, LayoutGrid, Microscope } from "lucide-react"

import { useLiveQuote } from "@/components/workspace/live-quote-provider"
import { useSavedStocks } from "@/features/saved-stocks/saved-stocks-provider"
import { useValuationAssumptions } from "@/features/valuation-assumptions/valuation-assumptions-provider"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { TerminalHeader } from "./components/terminal-header"
import { SaveStockButton } from "@/features/saved-stocks/save-stock-button"
import { AssetBasedCard } from "./components/AssetBasedCard"
import { DCFCard } from "./components/DCFCard"
import type { DCFData, ValuationTelemetry } from "./components/DCFCard"
import { DDMCard } from "./components/DDMCard"
import { RelativeCard } from "./components/RelativeCard"
import { RICard } from "./components/RICard"
import { EngineTelemetry } from "./components/engine-telemetry"
import { BridgeChart } from "./components/deep-dive/bridge-chart"
import { ProjectionTable } from "./components/deep-dive/projection-table"
import { SensitivityMatrix } from "./components/deep-dive/sensitivity-matrix"
import { TrajectoryChart } from "./components/deep-dive/trajectory-chart"
import { WaccArchitecture } from "./components/deep-dive/wacc-architecture"
import { RealityCheckBanner } from "./components/reality-check-banner"
import { SotpEvidenceNote } from "./components/sotp-evidence-note"
import { MonteCarloCurve } from "./components/simulation/monte-carlo-curve"
import { ReverseDcfSolver } from "./components/simulation/reverse-dcf-solver"
import { ValuationComparison, type ValuationComparisonItem } from "./components/valuation-comparison"
import {
  assumptionsFromResponse,
  DcfAssumptionWorkspace,
  type DcfAssumptionValues,
} from "./components/dcf-assumption-workspace"
import type { Scenario } from "@/lib/valuation"

const fetcher = (url: string) =>
  fetch(url, { signal: AbortSignal.timeout(90000) }).then(async (res) => {
    if (!res.ok) {
      let detail = `API error ${res.status}`;
      try {
        const body = await res.json();
        detail = body?.detail ? `${detail}: ${body.detail}` : detail;
      } catch {
        // keep the status-only message
      }
      throw new Error(detail);
    }
    return res.json();
  });

type Tab = "overview" | "dcf" | "sim"
type EngineResponse = {
  valuation_status?: string
  valuation_methodology?: string
  computed_fair_value?: number | null
  margin_of_safety_percentage?: number | null
  current_price?: number | null
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  sotp_breakdown?: any
  underlying_assumptions?: {
    missing_inputs?: string[]
    error?: string
    unavailable_reason?: string
    unavailable_reason_code?: string
    market_cap?: number
    beta?: number
    risk_free_rate?: number
    cost_of_equity?: number
    telemetry?: ValuationTelemetry
  }
}

function firstNumber(...values: Array<number | null | undefined>) {
  return values.find((value) => typeof value === "number" && Number.isFinite(value)) ?? null
}

function pickTelemetry(...responses: Array<EngineResponse | undefined>): ValuationTelemetry {
  for (const response of responses) {
    const telemetry = response?.underlying_assumptions?.telemetry
    if (telemetry && Object.keys(telemetry).length > 0) {
      return telemetry
    }
  }
  return {}
}

function formatMarketCap(value: number | null) {
  if (value === null) return null
  const abs = Math.abs(value)
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
}

function responseMatchesAssumptions(
  data: DCFData | undefined,
  values: DcfAssumptionValues | null,
) {
  if (!data || !values) return false
  const responseValues = assumptionsFromResponse(data)
  if (!responseValues) return false
  return (
    Math.abs(responseValues.growthRate - values.growthRate) < 0.001 &&
    Math.abs(responseValues.perpetualGrowthRate - values.perpetualGrowthRate) < 0.001 &&
    Math.abs(responseValues.discountRate - values.discountRate) < 0.001
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const tabs: { id: Tab; label: string; shortLabel: string; icon: any }[] = [
  { id: "overview", label: "Valuation Overview", shortLabel: "Overview", icon: LayoutGrid },
  { id: "dcf", label: "DCF Intrinsic Deep-Dive", shortLabel: "DCF", icon: Microscope },
  { id: "sim", label: "Simulation & Market Expectations", shortLabel: "Simulation", icon: Activity },
]

function EngineLoadingCard() {
  return (
    <GlassCard className="h-[320px] animate-pulse p-6 motion-reduce:animate-none">
      <div className="h-6 w-1/3 rounded-sm bg-[#1A2E20]" />
      <div className="mt-8 flex justify-between">
        <div className="h-10 w-1/4 rounded-sm bg-[#1A2E20]" />
        <div className="h-10 w-1/4 rounded-sm bg-[#1A2E20]" />
      </div>
      <div className="mt-8 h-36 rounded-sm bg-[#1A2E20]/50" />
    </GlassCard>
  )
}

function EngineStateCard({
  title,
  status,
  message,
  onRetry,
}: {
  title: string
  status: "Inputs unavailable" | "Inputs need attention" | "Model unavailable"
  message: string
  onRetry?: () => void
}) {
  const icon = status === "Inputs unavailable"
    ? <Database className="h-4 w-4" />
    : status === "Inputs need attention"
      ? <CircleAlert className="h-4 w-4" />
      : <CircleOff className="h-4 w-4" />

  return (
    <GlassCard>
      <CardHeading
        title={title}
        subtitle={status}
        icon={icon}
      />
      <div className="px-5 py-8 flex flex-col items-start gap-4">
        <p className="max-w-xl text-sm leading-6 text-[#869E8F]">{message}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="min-h-11 rounded-sm border border-[#1A2E20] bg-transparent px-4 py-2 text-xs font-semibold text-[#E0E6E2] transition-colors hover:bg-[#1A2E20]"
          >
            Retry
          </button>
        )}
      </div>
    </GlassCard>
  )
}

function renderEngine(
  title: string,
  data: EngineResponse | undefined,
  error: Error | undefined,
  isLoading: boolean,
  render: () => ReactNode,
  onRetry?: () => void,
) {
  if (data?.valuation_status === "MISSING_INPUT") {
    const missing = data.underlying_assumptions?.missing_inputs ?? [];
    return (
      <EngineStateCard
        title={title}
        status="Inputs unavailable"
        message={
          missing.length
            ? `Not calculated. Required sourced inputs are missing: ${missing.join(", ")}.`
            : "Not calculated because required sourced inputs are missing."
        }
        onRetry={onRetry}
      />
    )
  }

  if (data?.valuation_status === "INVALID_INPUT") {
    return (
      <EngineStateCard
        title={title}
        status="Inputs need attention"
        message={data.underlying_assumptions?.error ?? "Inputs failed validation."}
        onRetry={onRetry}
      />
    )
  }

  if (data?.valuation_status === "UNAVAILABLE") {
    return (
      <EngineStateCard
        title={title}
        status="Model unavailable"
        message={
          data.underlying_assumptions?.unavailable_reason
          ?? "The model completed but did not produce a usable fair value for this company."
        }
        onRetry={onRetry}
      />
    )
  }

  if (error) {
    return <EngineStateCard title={title} status="Model unavailable" message={error.message} onRetry={onRetry} />
  }

  if (isLoading && !data) {
    return <EngineLoadingCard />
  }

  return data ? render() : null
}

export function ValuationDashboard({ ticker }: { ticker: string }) {
  const [tab, setTab] = useState<Tab>("overview")
  const [scenario, setScenario] = useState<Scenario>("base")
  const [appliedAssumptions, setAppliedAssumptions] = useState<{
    ticker: string
    values: DcfAssumptionValues
  } | null>(null)
  const [persistenceState, setPersistenceState] = useState<{
    ticker: string
    status: "saving" | "account" | "device" | "pending" | "memory"
  } | null>(null)
  const [lastAcceptedScenario, setLastAcceptedScenario] = useState<{
    ticker: string
    data: DCFData
  } | null>(null)
  const [isResettingAssumptions, setIsResettingAssumptions] = useState(false)
  const [relativePeerState, setRelativePeerState] = useState<{
    ticker: string
    symbols: string[]
  } | null>(null)
  const reduceMotion = useReducedMotion()
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    overview: null,
    dcf: null,
    sim: null,
  })
  const { data: liveQuote } = useLiveQuote()
  const { isSaved } = useSavedStocks()
  const assumptionStore = useValuationAssumptions()
  const normalizedTicker = ticker.toUpperCase()
  const savedAssumption = assumptionStore.get(normalizedTicker)

  const activateTab = useCallback((nextTab: Tab, focusTab = false) => {
    setTab(nextTab)
    if (focusTab) {
      requestAnimationFrame(() => {
        const nextNode = tabRefs.current[nextTab]
        nextNode?.focus()
        nextNode?.scrollIntoView({ block: "nearest", inline: "nearest" })
      })
    }
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Switch tabs with Cmd/Ctrl + 1, 2, 3
      if (e.metaKey || e.ctrlKey) {
        switch (e.key) {
          case "1":
            e.preventDefault()
            activateTab("overview", true)
            break
          case "2":
            e.preventDefault()
            activateTab("dcf", true)
            break
          case "3":
            e.preventDefault()
            activateTab("sim", true)
            break
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [activateTab])

  const { data: summaryData } = useSWR(
    ticker ? `/api/stocks/${ticker.toUpperCase()}/summary` : null, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  // Concurrent SWR fetching — each engine is independent
  const { data: assetData, error: assetErr, isLoading: assetLoading, mutate: assetMutate } = useSWR(
    ticker ? `/api/v1/valuation/asset-based?ticker=${ticker.toUpperCase()}` : null, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
  const {
    data: baseDcfData,
    error: baseDcfErr,
    isLoading: baseDcfLoading,
    mutate: baseDcfMutate,
  } = useSWR<DCFData>(
    ticker ? `/api/v1/valuation/dcf?ticker=${normalizedTicker}` : null, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
  const savedAssumptionValues = savedAssumption
    ? {
        growthRate: savedAssumption.growthRate,
        perpetualGrowthRate: savedAssumption.perpetualGrowthRate,
        discountRate: savedAssumption.discountRate,
      }
    : null
  const activeAppliedAssumptions =
    appliedAssumptions?.ticker === normalizedTicker
      ? appliedAssumptions.values
      : savedAssumptionValues
  const scenarioDcfUrl = useMemo(() => {
    if (!ticker || !activeAppliedAssumptions) return null
    const params = new URLSearchParams({
      ticker: normalizedTicker,
      stage_1_growth_rate: String(activeAppliedAssumptions.growthRate / 100),
      perpetual_growth_rate: String(activeAppliedAssumptions.perpetualGrowthRate / 100),
      discount_rate: String(activeAppliedAssumptions.discountRate / 100),
    })
    return `/api/v1/valuation/dcf?${params.toString()}`
  }, [activeAppliedAssumptions, normalizedTicker, ticker])
  const {
    data: scenarioDcfData,
    error: scenarioDcfErr,
    isLoading: scenarioDcfLoading,
    isValidating: scenarioDcfValidating,
    mutate: scenarioDcfMutate,
  } = useSWR<DCFData>(scenarioDcfUrl, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
    keepPreviousData: true,
    onSuccess: (response) => {
      if (
        response.ticker === normalizedTicker &&
        responseMatchesAssumptions(response, activeAppliedAssumptions)
      ) {
        setLastAcceptedScenario({ ticker: normalizedTicker, data: response })
      }
    },
  })

  const baseAssumptions = useMemo(
    () => assumptionsFromResponse(baseDcfData),
    [baseDcfData],
  )

  const currentScenarioData =
    scenarioDcfData?.ticker === normalizedTicker &&
    responseMatchesAssumptions(scenarioDcfData, activeAppliedAssumptions)
      ? scenarioDcfData
      : null
  const retainedScenarioData = currentScenarioData ?? (
    lastAcceptedScenario?.ticker === normalizedTicker
      ? lastAcceptedScenario.data
      : null
  )
  const scenarioMismatchError = Boolean(
    activeAppliedAssumptions &&
    scenarioDcfData &&
    scenarioDcfData.ticker === normalizedTicker &&
    !currentScenarioData &&
    !scenarioDcfLoading &&
    !scenarioDcfValidating &&
    !scenarioDcfErr
  )
    ? new Error("The response assumptions did not match the requested inputs. Retry the model.")
    : undefined
  const scenarioRequestError = scenarioDcfErr ?? scenarioMismatchError
  const dcfData = activeAppliedAssumptions
    ? retainedScenarioData ?? baseDcfData
    : baseDcfData
  const dcfErr = dcfData ? undefined : activeAppliedAssumptions ? scenarioRequestError : baseDcfErr
  const dcfLoading = dcfData
    ? false
    : activeAppliedAssumptions
      ? scenarioDcfLoading
      : baseDcfLoading
  const dcfUpdating = Boolean(
    activeAppliedAssumptions &&
    (scenarioDcfLoading || scenarioDcfValidating),
  )
  const dcfMutate = () => (
    activeAppliedAssumptions ? scenarioDcfMutate() : baseDcfMutate()
  )
  const { data: ddmData, error: ddmErr, isLoading: ddmLoading, mutate: ddmMutate } = useSWR(
    ticker ? `/api/v1/valuation/ddm?ticker=${ticker.toUpperCase()}` : null, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );
  const selectedRelativePeerSymbols =
    relativePeerState?.ticker === normalizedTicker ? relativePeerState.symbols : null
  const relativeUrl = useMemo(() => {
    if (!ticker) return null
    const params = new URLSearchParams({ ticker: normalizedTicker })
    selectedRelativePeerSymbols?.forEach((symbol) => params.append("included_peer", symbol))
    return `/api/v1/valuation/relative?${params.toString()}`
  }, [normalizedTicker, selectedRelativePeerSymbols, ticker])
  const {
    data: relativeData,
    error: relativeErr,
    isLoading: relativeLoading,
    isValidating: relativeValidating,
    mutate: relativeMutate,
  } = useSWR(relativeUrl, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 30000,
    keepPreviousData: true,
  });
  const { data: riData, error: riErr, isLoading: riLoading, mutate: riMutate } = useSWR(
    ticker ? `/api/v1/valuation/residual-income?ticker=${ticker.toUpperCase()}` : null, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 30000 }
  );

  const livePrice = firstNumber(liveQuote?.data?.price)
  const marketReferencePrice = firstNumber(livePrice, dcfData?.current_price)
  const displayDcfData = dcfData
    ? { ...dcfData, current_price: marketReferencePrice }
    : undefined
  const telemetry = pickTelemetry(dcfData, relativeData, riData, assetData, ddmData)
  const marketCap = firstNumber(
    telemetry.market_cap,
    dcfData?.underlying_assumptions?.market_cap,
    relativeData?.underlying_assumptions?.market_cap,
    riData?.underlying_assumptions?.market_cap,
    assetData?.underlying_assumptions?.market_cap,
    ddmData?.underlying_assumptions?.market_cap,
  )
  const beta = firstNumber(telemetry.beta)
  const riskFreeRate = firstNumber(telemetry.risk_free_rate)
  const costOfEquity = firstNumber(telemetry.cost_of_equity)
  const marketCapSource = telemetry.market_cap_source
  const betaSource = telemetry.beta_source
  const riskFreeRateSource = telemetry.risk_free_rate_source
  const riskFreeRateAsOf = telemetry.risk_free_rate_as_of
  const comparisonItems: ValuationComparisonItem[] = [
    {
      id: "asset",
      method: "Asset-Based",
      status: assetData?.valuation_status,
      fairValue: assetData?.computed_fair_value,
      marginOfSafety: assetData?.margin_of_safety_percentage,
      isLoading: assetLoading,
      hasError: Boolean(assetErr),
    },
    {
      id: "dcf",
      method: "Discounted Cash Flow",
      methodology: dcfData?.valuation_methodology,
      status: dcfData?.valuation_status,
      fairValue: dcfData?.computed_fair_value,
      marginOfSafety: dcfData?.margin_of_safety_percentage,
      hasMaterialSensitivity:
        dcfData?.engine_metadata?.consensus_horizon_sensitivity?.warning_triggered === true,
      isLoading: dcfLoading,
      hasError: Boolean(dcfErr),
    },
    {
      id: "ddm",
      method: "Dividend Discount Model",
      status: ddmData?.valuation_status,
      fairValue: ddmData?.computed_fair_value,
      marginOfSafety: ddmData?.margin_of_safety_percentage,
      isLoading: ddmLoading,
      hasError: Boolean(ddmErr),
    },
    {
      id: "relative",
      method: "Relative Valuation",
      status: relativeData?.valuation_status,
      fairValue: relativeData?.computed_fair_value,
      marginOfSafety: relativeData?.margin_of_safety_percentage,
      isLoading: relativeLoading,
      hasError: Boolean(relativeErr),
    },
    {
      id: "ri",
      method: "Residual Income",
      status: riData?.valuation_status,
      fairValue: riData?.computed_fair_value,
      marginOfSafety: riData?.margin_of_safety_percentage,
      isLoading: riLoading,
      hasError: Boolean(riErr),
    },
  ]

  const reverseDcfSotp = dcfData?.reverse_dcf_sotp
  const isSotp = reverseDcfSotp?.is_active ?? false;
  const panelMotion = reduceMotion
    ? { initial: false as const, animate: { opacity: 1 }, exit: { opacity: 1 }, transition: { duration: 0 } }
    : {
        initial: { opacity: 0, y: 10 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -10 },
        transition: { duration: 0.15 },
      }

  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, current: Tab) => {
    const currentIndex = tabs.findIndex((item) => item.id === current)
    let nextIndex: number | null = null

    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
    if (event.key === "Home") nextIndex = 0
    if (event.key === "End") nextIndex = tabs.length - 1
    if (nextIndex === null) return

    event.preventDefault()
    const nextTab = tabs[nextIndex].id
    activateTab(nextTab, true)
  }

  // Flatten reverse_dcf_sotp fields to the top level so the SOTP-aware
  // components (RealityCheckBanner, SotpComposition, ReverseDcfSolver) receive
  // segments / required_cagr / net_cash where they expect them.
  const sotpData = isSotp && reverseDcfSotp
    ? {
        ...displayDcfData,
        ...reverseDcfSotp,
        target_price: reverseDcfSotp.target_price ?? undefined,
        shares_outstanding: dcfData?.underlying_assumptions?.shares_outstanding,
        required_cagr: reverseDcfSotp.implied_growth_rate ?? undefined,
      }
    : { ...displayDcfData, shares_outstanding: dcfData?.underlying_assumptions?.shares_outstanding };

  return (
    <div className="min-h-screen bg-[#0A0D0B] text-[#E0E6E2] font-sans">
      <TerminalHeader
        tickerSymbol={ticker.toUpperCase()}
        currentPrice={livePrice}
        marketCap={formatMarketCap(marketCap)}
        marketCapSource={marketCapSource}
        beta={beta}
        betaSource={betaSource}
        riskFreeRate={riskFreeRate !== null ? riskFreeRate * 100 : null}
        riskFreeRateSource={riskFreeRateSource}
        riskFreeRateAsOf={riskFreeRateAsOf}
        costOfEquity={costOfEquity !== null ? costOfEquity * 100 : null}
        logoUrl={summaryData?.data?.company_overview?.data?.logo_url as string | undefined}
        fmpLogoUrl={summaryData?.data?.company_overview?.data?.fmp_logo_url as string | undefined}
      />

      <main className="mx-auto max-w-[1600px] px-4 py-6 md:px-6">
        {dcfData?.valuation_status === "CALCULATED" && !isSaved(ticker.toUpperCase()) ? (
          <aside className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#B7FF3C]/20 bg-[#071710]/55 px-4 py-3" aria-label="Save this valuation workspace">
            <div>
              <p className="text-sm font-semibold text-[#EFFAF4]">Return when {ticker.toUpperCase()} inputs or market expectations change.</p>
              <p className="mt-1 text-xs text-[#869E8F]">Save the company route; valuation results are always recalculated from current sourced inputs.</p>
            </div>
            <SaveStockButton ticker={ticker.toUpperCase()} section="valuation" />
          </aside>
        ) : null}
        {/* Tab group */}
        <div className="mb-4 max-w-full">
        <div role="tablist" aria-label="Valuation views" aria-orientation="horizontal" className="grid w-full grid-cols-3 rounded-md border border-[#1A2E20] bg-[#111613] p-1">
          {tabs.map((t) => {
            const active = tab === t.id
            const Icon = t.icon
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-label={t.label}
                aria-selected={active}
                aria-controls={`valuation-panel-${t.id}`}
                id={`valuation-tab-${t.id}`}
                onClick={() => activateTab(t.id)}
                onKeyDown={(event) => handleTabKeyDown(event, t.id)}
                ref={(node) => { tabRefs.current[t.id] = node }}
                tabIndex={active ? 0 : -1}
                className={`relative flex min-h-11 min-w-0 items-center justify-center gap-1.5 rounded-sm px-1 py-2 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B7FF3C] focus-visible:ring-inset sm:gap-2 sm:px-4 sm:text-sm ${
                  active
                    ? "bg-[#1A2E20] text-[#E0E6E2]"
                    : "text-[#869E8F] hover:text-[#E0E6E2]"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-emerald-400" : ""}`} />
                <span className="truncate sm:hidden">{t.shortLabel}</span>
                <span className="hidden truncate sm:inline">{t.label}</span>
              </button>
            )
          })}
        </div>
        </div>

        <DcfAssumptionWorkspace
          ticker={normalizedTicker}
          methodologyData={dcfData}
          base={baseAssumptions}
          applied={activeAppliedAssumptions}
          isUpdating={dcfUpdating}
          isResetting={isResettingAssumptions}
          requestError={scenarioRequestError}
          persistenceLabel={
            assumptionStore.loading
              ? "Restoring saved assumptions"
              : persistenceState?.ticker !== normalizedTicker
                ? savedAssumption
                  ? assumptionStore.mode === "authenticated" ? "Saved to account" : "Saved on this device"
                  : null
                : persistenceState.status === "saving"
                  ? "Saving assumptions"
                  : persistenceState.status === "account"
                    ? "Saved to account"
                    : persistenceState.status === "device"
                      ? "Saved on this device"
                      : persistenceState.status === "memory"
                        ? "Applied for this visit"
                        : "Saved on device · sync pending"
          }
          persistenceError={assumptionStore.error}
          onApply={(values) => {
            setAppliedAssumptions({ ticker: normalizedTicker, values })
            setPersistenceState({ ticker: normalizedTicker, status: "saving" })
            void assumptionStore.save(normalizedTicker, values).then((result) => {
              setPersistenceState({
                ticker: normalizedTicker,
                status: result.ok
                  ? result.persistedTo
                  : result.persistedTo === "device" ? "pending" : "memory",
              })
            })
          }}
          onReset={() => {
            setIsResettingAssumptions(true)
            void assumptionStore.remove(normalizedTicker).then((result) => {
              if (result.ok) {
                setAppliedAssumptions(null)
                setPersistenceState(null)
                setScenario("base")
              }
            }).finally(() => setIsResettingAssumptions(false))
          }}
          onRetryModel={() => void scenarioDcfMutate()}
          onRetryPersistence={() => void assumptionStore.retry()}
        />

        <AnimatePresence mode="wait">
          {tab === "overview" && (
            <motion.div
              key="overview"
              id="valuation-panel-overview"
              role="tabpanel"
              aria-labelledby="valuation-tab-overview"
              {...panelMotion}
              className="grid grid-cols-1 gap-6 xl:grid-cols-2"
            >
              <div className="xl:col-span-2 flex flex-col gap-6">
              <ValuationComparison items={comparisonItems} marketPrice={marketReferencePrice} />
              {dcfData?.valuation_status === "CALCULATED" ? <RealityCheckBanner data={sotpData} /> : null}
              {dcfData?.valuation_status !== "CALCULATED" ? (
                renderEngine("Adaptive Valuation Engine", dcfData, dcfErr, dcfLoading, () => null, () => dcfMutate())
              ) : <details className="rounded-md border border-[#1A2E20] bg-[#111613]">
                <summary className="flex min-h-11 cursor-pointer items-center px-5 py-3 text-sm font-semibold text-[#C8D4CC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#B7FF3C]">
                  Methodology, calculation basis &amp; composition
                </summary>
                <div className="flex flex-col gap-6 border-t border-[#1A2E20] p-3 sm:p-4">
                  {renderEngine("Adaptive Valuation Engine", dcfData, dcfErr, dcfLoading, () => (
                    <EngineTelemetry data={displayDcfData!} />
                  ), () => dcfMutate())}
                  {dcfData?.valuation_status === "CALCULATED" ? <SotpEvidenceNote data={dcfData?.sotp_breakdown} /> : null}
                </div>
              </details>}
            </div>
            {renderEngine("Asset-Based Valuation", assetData, assetErr, assetLoading, () => (
              <AssetBasedCard data={assetData} />
            ), () => assetMutate())}
            {renderEngine("Discounted Cash Flow (DCF)", dcfData, dcfErr, dcfLoading, () => (
              <DCFCard
                data={displayDcfData!}
              />
            ), () => dcfMutate())}
            {renderEngine("Dividend Discount Model (DDM)", ddmData, ddmErr, ddmLoading, () => (
              <DDMCard data={ddmData} />
            ), () => ddmMutate())}
            {renderEngine("Relative Valuation", relativeData, relativeErr, relativeLoading, () => (
              <RelativeCard
                data={relativeData}
                selectedPeerSymbols={selectedRelativePeerSymbols}
                isUpdating={Boolean(selectedRelativePeerSymbols && relativeValidating)}
                onPeerSelectionChange={(symbols) => {
                  setRelativePeerState({ ticker: normalizedTicker, symbols })
                }}
              />
            ), () => relativeMutate())}
            <div className="xl:col-span-2">
              {renderEngine("Residual Income Model (RI)", riData, riErr, riLoading, () => (
                <RICard data={riData} />
              ), () => riMutate())}
            </div>
          </motion.div>
          )}
          {tab === "dcf" && (
            <motion.div
              key="dcf"
              id="valuation-panel-dcf"
              role="tabpanel"
              aria-labelledby="valuation-tab-dcf"
              {...panelMotion}
              className="flex flex-col gap-6"
            >
              <h2 className="sr-only">DCF intrinsic deep-dive</h2>
              {dcfData?.valuation_status === "CALCULATED" ? (
              <>
                <BridgeChart data={displayDcfData!} />

                <WaccArchitecture data={displayDcfData!} />

                <TrajectoryChart
                  key={scenario}
                  scenario={scenario}
                  data={displayDcfData!}
                />

                <ProjectionTable
                  scenario={scenario} 
                  onScenarioChange={setScenario} 
                  dcfData={displayDcfData!}
                />
                
                <SensitivityMatrix 
                  data={displayDcfData!}
                  isUpdating={dcfUpdating}
                  onRetry={() => void dcfMutate()}
                />
              </>
            ) : (
              renderEngine("DCF Intrinsic Deep-Dive", dcfData, dcfErr, dcfLoading, () => null, () => dcfMutate())
            )}
          </motion.div>
          )}
          {tab === "sim" && (
            <motion.div
              key="sim"
              id="valuation-panel-sim"
              role="tabpanel"
              aria-labelledby="valuation-tab-sim"
              {...panelMotion}
              className="flex flex-col gap-6"
            >
              <h2 className="sr-only">Simulation and market expectations</h2>
              {dcfData?.valuation_status === "CALCULATED" ? (
              <>
                {dcfData.engine_metadata?.consensus_horizon_sensitivity?.warning_triggered === true ? (
                  <div className="rounded-md border border-[#294231] bg-[#0A0D0B] px-4 py-3 text-xs leading-5 text-[#9AB0A1]">
                    Monte Carlo and Reverse DCF below use the same full-consensus model as the primary DCF result. The without-last-year value is diagnostic only.
                  </div>
                ) : null}
                <MonteCarloCurve
                  data={displayDcfData!}
                  isUpdating={dcfUpdating}
                  onRetry={() => void dcfMutate()}
                />
                <ReverseDcfSolver data={sotpData} />
              </>
            ) : (
              renderEngine("Simulation & Market Expectations", dcfData, dcfErr, dcfLoading, () => null, () => dcfMutate())
            )}
          </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  )
}
