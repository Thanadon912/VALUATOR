"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import Link from "next/link"
import useSWR from "swr"
import { ArrowUpRight, Check, Database, LoaderCircle } from "lucide-react"
import {
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
  type MotionValue,
} from "framer-motion"

const stages = [
  {
    id: "evidence",
    label: "Evidence",
    title: "The record arrives first.",
    copy: "Provider responses, filing periods, and timestamps establish the boundary of the analysis before a model is allowed to speak.",
  },
  {
    id: "assumptions",
    label: "Model basis",
    title: "Facts and judgment stay apart.",
    copy: "Market inputs and reported financials remain traceable while discount rates and model choices are presented as assumptions—not facts.",
  },
  {
    id: "methods",
    label: "Simulation",
    title: "Uncertainty, made visible.",
    copy: "10,000 Monte Carlo paths frame DCF uncertainty; five independent engines keep that range in economic context.",
  },
  {
    id: "expectations",
    label: "Price implied",
    title: "Then the market gets questioned.",
    copy: "The live price enters last. When the solver can reconcile price and model, VALUATOR exposes the growth and margin the market requires.",
  },
] as const

const stageAnchors = stages.map((_, index) => index / (stages.length - 1))
const magneticCaptureRange = 0.2 / (stages.length - 1)

type JsonRecord = Record<string, unknown>
type EngineKey = "asset" | "dcf" | "ddm" | "relative" | "residual"

type FeaturedResponse = {
  ticker: string
  company_name: string | null
  fetched_at: string
  cache_ttl_seconds: number
  status: "complete" | "partial" | "unavailable"
  providers: string[]
  engines: Record<EngineKey, JsonRecord | null>
  warnings: string[]
}

type MethodDatum = {
  key: EngineKey
  label: string
  value: number | null
  low: number | null
  median: number | null
  high: number | null
  status: string
  methodology: string | null
}

const methodLabels: Record<EngineKey, string> = {
  asset: "Asset",
  dcf: "Adaptive DCF",
  ddm: "Dividend",
  relative: "Relative",
  residual: "Residual income",
}

const fetcher = async (url: string): Promise<FeaturedResponse> => {
  const response = await fetch(url, { signal: AbortSignal.timeout(95000) })
  if (!response.ok) throw new Error(`Featured walkthrough returned ${response.status}`)
  return response.json() as Promise<FeaturedResponse>
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function recordAt(parent: JsonRecord | null | undefined, key: string) {
  const value = parent?.[key]
  return isRecord(value) ? value : undefined
}

function finiteNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function formatMoney(value: number | null) {
  if (value === null) return "Unavailable"
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value)
}

function formatPercent(value: number | null) {
  if (value === null) return "Unavailable"
  return `${(value * 100).toFixed(1)}%`
}

function formatTimestamp(value: string | undefined) {
  if (!value) return "Timestamp unavailable"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable"
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed)
}

function buildMethods(data: FeaturedResponse | undefined): MethodDatum[] {
  const keys: EngineKey[] = ["asset", "dcf", "ddm", "relative", "residual"]
  return keys.map((key) => {
    const engine = data?.engines[key] ?? null
    const monteCarlo = recordAt(engine, "monte_carlo_results")
    return {
      key,
      label: methodLabels[key],
      value: finiteNumber(engine?.computed_fair_value),
      low: key === "dcf" ? finiteNumber(monteCarlo?.bear_p10) : null,
      median: key === "dcf" ? finiteNumber(monteCarlo?.base_p50) : null,
      high: key === "dcf" ? finiteNumber(monteCarlo?.bull_p90) : null,
      status: typeof engine?.valuation_status === "string" ? engine.valuation_status : "UNAVAILABLE",
      methodology: typeof engine?.valuation_methodology === "string" ? engine.valuation_methodology : null,
    }
  })
}

export function MarketExpectationsInstrument() {
  const desktopSceneRef = useRef<HTMLDivElement>(null)
  const scrollAnimationRef = useRef(0)
  const [activeIndex, setActiveIndex] = useState(0)
  const reduceMotion = useReducedMotion()
  const scrollYProgress = useMotionValue(0)
  const { data, error, isLoading } = useSWR("/api/featured-walkthrough", fetcher, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: 60 * 60 * 1000,
    keepPreviousData: true,
  })

  const scrollToStage = useCallback((index: number) => {
    const scene = desktopSceneRef.current
    if (!scene) return

    cancelAnimationFrame(scrollAnimationRef.current)
    const startY = window.scrollY
    const sceneTop = startY + scene.getBoundingClientRect().top
    const distance = Math.max(1, scene.offsetHeight - window.innerHeight)
    const targetY = sceneTop + stageAnchors[index] * distance

    if (reduceMotion) {
      window.scrollTo({ top: targetY })
      return
    }

    const duration = 380
    const startedAt = performance.now()
    const tick = (now: number) => {
      const elapsed = Math.min(1, (now - startedAt) / duration)
      const eased = 1 - Math.pow(1 - elapsed, 5)
      window.scrollTo(0, startY + (targetY - startY) * eased)
      if (elapsed < 1) {
        scrollAnimationRef.current = requestAnimationFrame(tick)
      } else {
        scrollAnimationRef.current = 0
      }
    }
    scrollAnimationRef.current = requestAnimationFrame(tick)
  }, [reduceMotion])

  useEffect(() => {
    const scene = desktopSceneRef.current
    if (!scene || reduceMotion) return

    let frame = 0
    let settleTimer = 0
    const measure = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const rect = scene.getBoundingClientRect()
        const distance = Math.max(1, scene.offsetHeight - window.innerHeight)
        const progress = Math.min(1, Math.max(0, -rect.top / distance))
        scrollYProgress.set(progress)
        const nextIndex = Math.min(stages.length - 1, Math.round(progress * (stages.length - 1)))
        setActiveIndex((current) => current === nextIndex ? current : nextIndex)
      })
    }

    const settle = () => {
      if (scrollAnimationRef.current) return
      const rect = scene.getBoundingClientRect()
      const distance = Math.max(1, scene.offsetHeight - window.innerHeight)
      const rawProgress = -rect.top / distance
      if (rawProgress < 0 || rawProgress > 1) return
      const nearestIndex = Math.min(stages.length - 1, Math.round(rawProgress * (stages.length - 1)))
      const anchorDistance = Math.abs(rawProgress - stageAnchors[nearestIndex])
      if (anchorDistance > 0.002 && anchorDistance <= magneticCaptureRange) scrollToStage(nearestIndex)
    }

    const handleScroll = () => {
      measure()
      window.clearTimeout(settleTimer)
      if (!scrollAnimationRef.current) settleTimer = window.setTimeout(settle, 150)
    }

    const cancelSettle = () => {
      cancelAnimationFrame(scrollAnimationRef.current)
      scrollAnimationRef.current = 0
      window.clearTimeout(settleTimer)
    }

    measure()
    window.addEventListener("scroll", handleScroll, { passive: true })
    window.addEventListener("resize", measure)
    window.addEventListener("wheel", cancelSettle, { passive: true })
    window.addEventListener("touchstart", cancelSettle, { passive: true })
    window.addEventListener("pointerdown", cancelSettle, { passive: true })
    window.addEventListener("keydown", cancelSettle)
    return () => {
      cancelAnimationFrame(frame)
      cancelAnimationFrame(scrollAnimationRef.current)
      window.clearTimeout(settleTimer)
      window.removeEventListener("scroll", handleScroll)
      window.removeEventListener("resize", measure)
      window.removeEventListener("wheel", cancelSettle)
      window.removeEventListener("touchstart", cancelSettle)
      window.removeEventListener("pointerdown", cancelSettle)
      window.removeEventListener("keydown", cancelSettle)
    }
  }, [reduceMotion, scrollToStage, scrollYProgress])

  const displayedIndex = reduceMotion ? stages.length - 1 : activeIndex
  const activeStage = stages[displayedIndex]

  return (
    <section id="instrument" className="valuator-instrument relative bg-[#0A0A09]">
      <div ref={desktopSceneRef} data-instrument-scene className={`instrument-scroll-scene relative hidden lg:block ${reduceMotion ? "instrument-scroll-scene--static" : ""}`}>
        <span id="methods-desktop" className="pointer-events-none absolute left-0 top-1/2" aria-hidden="true" />
        <div className="mx-auto grid w-full max-w-[90rem] grid-cols-[minmax(20rem,0.7fr)_minmax(36rem,1.3fr)] items-start gap-14 px-8 xl:gap-20">
          <div className="instrument-narrative">
            {reduceMotion ? (
              <StaticNarrative stage={activeStage} index={displayedIndex} />
            ) : stages.map((stage, index) => (
              <ScrollNarrative key={stage.id} stage={stage} index={index} progress={scrollYProgress} />
            ))}
          </div>
          <div className="instrument-pinned">
            <InstrumentFace
              activeIndex={displayedIndex}
              data={data}
              error={error}
              isLoading={isLoading}
              progress={scrollYProgress}
              onSelectStage={scrollToStage}
              reduceMotion={Boolean(reduceMotion)}
            />
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[48rem] px-5 py-16 sm:px-8 lg:hidden">
        {stages.map((stage, index) => (
          <article key={stage.id} id={stage.id === "methods" ? "methods-mobile" : undefined} data-instrument-stage={stage.id} className="instrument-stage border-t border-white/12 py-14 first:border-t-0">
            <div className="flex items-center gap-4"><span className="font-mono text-xs text-[#B7FF3C]">0{index + 1}</span><span className="text-sm font-semibold text-[#D8D8D0]">{stage.label}</span></div>
            <h2 className="valuator-display mt-6 max-w-[11ch] text-balance text-[clamp(2.8rem,12vw,4.4rem)] font-semibold leading-[0.94] tracking-[-0.035em] text-[#F2F2EE]">{stage.title}</h2>
            <p className="mt-6 max-w-[35rem] text-pretty text-base leading-7 text-[#BDBDB6]">{stage.copy}</p>
            <div className="mt-9"><InstrumentFace activeIndex={index} data={data} error={error} isLoading={isLoading} reduceMotion /></div>
          </article>
        ))}
      </div>

      <SourceLedger />
    </section>
  )
}

function StaticNarrative({ stage, index }: { stage: (typeof stages)[number]; index: number }) {
  return (
    <article className="instrument-narrative-static flex flex-col justify-center">
      <NarrativeContent stage={stage} index={index} />
    </article>
  )
}

function ScrollNarrative({ stage, index, progress }: { stage: (typeof stages)[number]; index: number; progress: MotionValue<number> }) {
  const anchor = stageAnchors[index]
  const enterMidpoint = index === 0 ? 0 : (stageAnchors[index - 1] + anchor) / 2
  const exitMidpoint = index === stages.length - 1 ? 1 : (anchor + stageAnchors[index + 1]) / 2
  const enterStart = Math.max(0, enterMidpoint - 0.055)
  const enterEnd = Math.min(1, enterMidpoint + 0.055)
  const exitStart = Math.max(0, exitMidpoint - 0.055)
  const exitEnd = Math.min(1, exitMidpoint + 0.055)
  const input = index === 0 ? [0, exitStart, exitEnd] : index === stages.length - 1 ? [enterStart, enterEnd, 1] : [enterStart, enterEnd, exitStart, exitEnd]
  const opacityOutput = index === 0 ? [1, 1, 0.3] : index === stages.length - 1 ? [0.3, 1, 1] : [0.3, 1, 1, 0.3]
  const yOutput = index === 0 ? [0, 0, -12] : index === stages.length - 1 ? [18, 0, 0] : [18, 0, 0, -12]
  const blurOutput = index === 0 ? ["blur(0px)", "blur(0px)", "blur(2.5px)"] : index === stages.length - 1 ? ["blur(2.5px)", "blur(0px)", "blur(0px)"] : ["blur(2.5px)", "blur(0px)", "blur(0px)", "blur(2.5px)"]
  const opacity = useTransform(progress, input, opacityOutput)
  const y = useTransform(progress, input, yOutput)
  const filter = useTransform(progress, input, blurOutput)

  return (
    <motion.article className="instrument-narrative-step flex flex-col justify-center" style={{ opacity, y, filter }}>
      <NarrativeContent stage={stage} index={index} />
    </motion.article>
  )
}

function NarrativeContent({ stage, index }: { stage: (typeof stages)[number]; index: number }) {
  return (
    <>
      <div className="flex items-center gap-4">
        <span className="font-mono text-xs text-[#B7FF3C]">0{index + 1}</span>
        <span className="text-sm font-semibold text-[#D8D8D0]">{stage.label}</span>
      </div>
      <h2 className="valuator-display mt-7 max-w-[10ch] text-balance text-[clamp(3.15rem,4.15vw,4.85rem)] font-semibold leading-[0.94] tracking-[-0.035em] text-[#F2F2EE]">{stage.title}</h2>
      <p className="mt-7 max-w-[32rem] text-pretty text-lg leading-8 text-[#BDBDB6]">{stage.copy}</p>
    </>
  )
}

function InstrumentFace({
  activeIndex,
  data,
  error,
  isLoading,
  progress,
  onSelectStage,
  reduceMotion = false,
}: {
  activeIndex: number
  data: FeaturedResponse | undefined
  error: Error | undefined
  isLoading: boolean
  progress?: MotionValue<number>
  onSelectStage?: (index: number) => void
  reduceMotion?: boolean
}) {
  const methods = useMemo(() => buildMethods(data), [data])
  const dcf = data?.engines.dcf ?? null
  const assumptions = recordAt(dcf, "underlying_assumptions")
  const telemetry = recordAt(assumptions, "telemetry")
  const implied = recordAt(dcf, "implied_expectations")
  const warnings = Array.isArray(assumptions?.computational_warnings)
    ? assumptions.computational_warnings.filter((item): item is string => typeof item === "string")
    : []
  const ticker = data?.ticker ?? "MSFT"
  const currentPrice = finiteNumber(dcf?.current_price) ?? finiteNumber(telemetry?.current_price)
  const validMethods = methods.filter((method) => method.value !== null)
  const loading = isLoading && !data
  const unavailable = Boolean(error) || data?.status === "unavailable"
  const stageIndex = activeIndex
  const stage = stages[stageIndex].id
  const stageProgress = (stageIndex + 1) / stages.length
  const fallbackProgress = useMotionValue(stageIndex / (stages.length - 1))
  const chapterProgress = progress ?? fallbackProgress
  const chapterIndicatorX = useTransform(chapterProgress, [0, 1], ["0%", "300%"])
  return (
    <div className="instrument-face relative overflow-hidden border border-white/16 bg-[#0D0D0C]">
      <header className="relative z-10 border-b border-white/12 p-5 sm:px-6 sm:py-5">
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-xs font-semibold text-[#B7FF3C]">FEATURED WALKTHROUGH · {ticker}</p>
            <p className="mt-2 text-sm text-[#A9A9A2]">
              {data?.company_name ?? (loading ? "Loading validated company record" : "Validated company record")}
            </p>
          </div>
          <div aria-live="polite"><StatusBadge loading={loading} unavailable={unavailable} partial={data?.status === "partial"} /></div>
        </div>
        <div className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-5 border-t border-white/10 pt-3 text-xs">
          <ReadoutInline label="Resolved" value={`${validMethods.length} / 5`} />
          <ReadoutInline label="Data as of" value={data ? formatTimestamp(data.fetched_at) : "Awaiting data"} align="right" />
        </div>
      </header>

      {onSelectStage ? (
        <nav className="instrument-chapter-nav relative border-b border-white/12" aria-label="Walkthrough chapters">
          <div className="grid grid-cols-4">
            {stages.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={`instrument-chapter-button min-h-12 border-r border-white/10 px-3 text-left text-xs font-semibold last:border-r-0 ${index === stageIndex ? "text-[#F2F2EE]" : index < stageIndex ? "text-[#9EBC8C]" : "text-[#85857F]"}`}
                aria-current={index === stageIndex ? "step" : undefined}
                onClick={() => onSelectStage(index)}
              >
                <span className="mr-2 font-mono text-[0.65rem] text-[#B7FF3C]">0{index + 1}</span>{item.label}
              </button>
            ))}
          </div>
          <motion.span className="pointer-events-none absolute bottom-0 left-0 h-0.5 w-1/4 bg-[#B7FF3C]" style={{ x: chapterIndicatorX }} />
        </nav>
      ) : (
        <div
          className="relative h-1 overflow-hidden border-b border-white/12 bg-white/10"
          role="progressbar"
          aria-label="Walkthrough progress"
          aria-valuemin={0}
          aria-valuemax={4}
          aria-valuenow={stageIndex + 1}
          aria-valuetext={`Stage ${stageIndex + 1} of 4`}
        >
          <div className="absolute inset-0 origin-left bg-[#B7FF3C]" style={{ transform: `scaleX(${stageProgress})` }} />
        </div>
      )}

      <div className="instrument-viewport relative min-h-0 p-5 sm:p-6 xl:p-7">
        {loading ? <LoadingState /> : unavailable ? <UnavailableState ticker={ticker} /> : null}
        {!loading && !unavailable && reduceMotion ? (
          <div className="h-full">
            {stage === "evidence" ? <EvidenceState data={data} methods={methods} /> : null}
            {stage === "assumptions" ? <AssumptionsState assumptions={assumptions} telemetry={telemetry} /> : null}
            {stage === "methods" ? <MethodsState methods={methods} reduceMotion /> : null}
            {stage === "expectations" ? <ExpectationsState methods={methods} currentPrice={currentPrice} implied={implied} warnings={warnings} reduceMotion /> : null}
          </div>
        ) : null}
        {!loading && !unavailable && !reduceMotion && progress ? (
          <div className="instrument-layer-stack h-full">
            <InstrumentLayer index={0} activeIndex={activeIndex} progress={progress}><EvidenceState data={data} methods={methods} /></InstrumentLayer>
            <InstrumentLayer index={1} activeIndex={activeIndex} progress={progress}><AssumptionsState assumptions={assumptions} telemetry={telemetry} /></InstrumentLayer>
            <InstrumentLayer index={2} activeIndex={activeIndex} progress={progress}><MethodsState methods={methods} progress={progress} reduceMotion={false} /></InstrumentLayer>
            <InstrumentLayer index={3} activeIndex={activeIndex} progress={progress}><ExpectationsState methods={methods} currentPrice={currentPrice} implied={implied} warnings={warnings} progress={progress} reduceMotion={false} /></InstrumentLayer>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function InstrumentLayer({ index, activeIndex, progress, children }: { index: number; activeIndex: number; progress: MotionValue<number>; children: ReactNode }) {
  const anchor = stageAnchors[index]
  const enterMidpoint = index === 0 ? 0 : (stageAnchors[index - 1] + anchor) / 2
  const exitMidpoint = index === stages.length - 1 ? 1 : (anchor + stageAnchors[index + 1]) / 2
  const input = index === 0
    ? [0, exitMidpoint - 0.045, exitMidpoint + 0.045]
    : index === stages.length - 1
      ? [enterMidpoint - 0.045, enterMidpoint + 0.045, 1]
      : [enterMidpoint - 0.045, enterMidpoint + 0.045, exitMidpoint - 0.045, exitMidpoint + 0.045]
  const opacityOutputs = index === 0 ? [1, 1, 0] : index === stages.length - 1 ? [0, 1, 1] : [0, 1, 1, 0]
  const yOutputs = index === 0 ? [0, 0, -10] : index === stages.length - 1 ? [14, 0, 0] : [14, 0, 0, -10]
  const opacity = useTransform(progress, input, opacityOutputs)
  const y = useTransform(progress, input, yOutputs)

  return (
    <motion.div className="instrument-layer absolute inset-0" style={{ opacity, y }} aria-hidden={activeIndex !== index}>
      {children}
    </motion.div>
  )
}

function StatusBadge({ loading, unavailable, partial }: { loading: boolean; unavailable: boolean; partial: boolean }) {
  if (loading) return <span className="flex items-center gap-2 font-mono text-xs font-bold text-[#D8D8D0]"><LoaderCircle className="size-3.5 animate-spin" />VALIDATING</span>
  if (unavailable) return <span className="flex items-center gap-2 font-mono text-xs font-bold text-[#A9C6B3]"><Database className="size-3.5" />UNAVAILABLE</span>
  return <span className="flex items-center gap-2 font-mono text-xs font-bold text-[#B7FF3C]"><Check className="size-3.5" />{partial ? "PARTIAL" : "VALIDATED"}</span>
}

function LoadingState() {
  return (
    <div className="flex min-h-[26rem] flex-col justify-between">
      <div>
        <p className="text-sm font-semibold text-[#F2F2EE]">Validating the featured record</p>
        <p className="mt-2 max-w-md text-sm leading-6 text-[#A9A9A2]">The walkthrough is requesting cached provider responses. No valuation geometry is drawn until those inputs return.</p>
      </div>
      <div className="space-y-3" aria-hidden="true">
        {["Company record", "Market telemetry", "Valuation engines"].map((label) => (
          <div key={label} className="flex items-center gap-4 border-b border-white/12 py-4 text-sm text-[#A9A9A2]"><LoaderCircle className="size-4 animate-spin text-[#B7FF3C]" />{label}</div>
        ))}
      </div>
    </div>
  )
}

function UnavailableState({ ticker }: { ticker: string }) {
  return (
    <div className="flex min-h-[26rem] flex-col items-start justify-center">
      <Database className="size-6 text-[#A9C6B3]" />
      <h3 className="mt-5 text-xl font-semibold text-[#F2F2EE]">Featured data is unavailable.</h3>
      <p className="mt-3 max-w-md text-sm leading-6 text-[#A9A9A2]">VALUATOR did not substitute demo values. Open the workspace to retry the real {ticker} analysis.</p>
      <Link href={`/stocks/${ticker}/valuation`} className="mt-7 inline-flex min-h-11 items-center gap-2 border-b border-[#B7FF3C] font-semibold text-[#B7FF3C]">Open {ticker} workspace <ArrowUpRight className="size-4" /></Link>
    </div>
  )
}

function EvidenceState({ data, methods }: { data: FeaturedResponse | undefined; methods: MethodDatum[] }) {
  const returned = methods.filter((method) => method.status !== "UNAVAILABLE").length
  const providers = data?.providers.slice(0, 4) ?? []
  return (
    <div>
      <StateHeading title="Provider record" copy="Only returned provider values enter the walkthrough." />
      <div className="mt-8 grid gap-px border border-white/12 bg-white/12 sm:grid-cols-2">
        <EvidenceCell label="Ticker" value={data?.ticker ?? "Unavailable"} />
        <EvidenceCell label="Engine responses" value={`${returned} of 5 returned`} />
        <EvidenceCell label="Response timestamp" value={formatTimestamp(data?.fetched_at)} />
        <EvidenceCell label="Cache policy" value="1 hour · background refresh" />
      </div>
      <div className="mt-6">
        <p className="text-xs font-semibold text-[#A9A9A2]">Providers reported by the response</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {providers.length ? providers.map((provider) => <span key={provider} className="border border-white/16 px-3 py-2 text-xs text-[#D8D8D0]">{provider}</span>) : <span className="text-sm text-[#A9A9A2]">Provider names unavailable in this response.</span>}
        </div>
      </div>
    </div>
  )
}

function AssumptionsState({ assumptions, telemetry }: { assumptions: JsonRecord | undefined; telemetry: JsonRecord | undefined }) {
  const rows = [
    ["Risk-free rate", formatPercent(finiteNumber(assumptions?.risk_free_rate) ?? finiteNumber(telemetry?.risk_free_rate)), "Provider input"],
    ["Market risk premium", formatPercent(finiteNumber(assumptions?.market_risk_premium) ?? finiteNumber(telemetry?.market_risk_premium)), "Global assumption"],
    ["Cost of equity", formatPercent(finiteNumber(assumptions?.cost_of_equity) ?? finiteNumber(telemetry?.cost_of_equity)), "Derived"],
    ["Discount rate / WACC", formatPercent(finiteNumber(assumptions?.wacc)), "Model assumption"],
  ]
  return (
    <div>
      <StateHeading title="Classification stays visible" copy="Provider inputs, global assumptions, and derived rates retain different labels." />
      <div className="mt-8 border-y border-white/12">
        {rows.map(([label, value, kind]) => (
          <div key={label} className="grid grid-cols-[1fr_auto] gap-4 border-b border-white/12 py-4 last:border-b-0 sm:grid-cols-[1fr_8rem_9rem]">
            <span className="text-sm text-[#D8D8D0]">{label}</span>
            <strong className="font-mono text-sm text-[#F2F2EE]">{value}</strong>
            <span className="col-span-2 text-xs text-[#A9A9A2] sm:col-span-1">{kind}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function MethodsState({ methods, reduceMotion, progress }: { methods: MethodDatum[]; reduceMotion: boolean; progress?: MotionValue<number> }) {
  const dcf = methods.find((method) => method.key === "dcf")
  return (
    <div className="instrument-state instrument-state--methods">
      <StateHeading title="DCF uncertainty, made visible" copy="10,000 simulations perturb growth and operating margin using historical volatility." />
      <MonteCarloRange method={dcf} progress={progress} reduceMotion={reduceMotion} />
      <ValuationPlot methods={methods} currentPrice={null} compact progress={progress} reduceMotion={reduceMotion} />
    </div>
  )
}

function ExpectationsState({ methods, currentPrice, implied, warnings, reduceMotion, progress }: { methods: MethodDatum[]; currentPrice: number | null; implied: JsonRecord | undefined; warnings: string[]; reduceMotion: boolean; progress?: MotionValue<number> }) {
  const growth = finiteNumber(implied?.implied_stage_1_revenue_cagr ?? implied?.implied_revenue_cagr)
  const margin = finiteNumber(implied?.implied_target_ebit_margin ?? implied?.implied_operating_margin)
  const converged = growth !== null || margin !== null
  return (
    <div>
      <StateHeading title={converged ? "Market expectations resolved" : "Solver result unavailable"} copy={converged ? "The market price is compared with the returned valuation outputs and the feasible solver result." : "The response did not contain a feasible implied-expectations solution. No result has been invented."} />
      <ValuationPlot methods={methods} currentPrice={currentPrice} compact progress={progress} reduceMotion={reduceMotion} />
      <div className="mt-5 grid gap-px border border-white/12 bg-white/12 sm:grid-cols-3">
        <ExpectationCell label="Market price" value={formatMoney(currentPrice)} />
        <ExpectationCell label="Required stage-1 growth" value={formatPercent(growth)} />
        <ExpectationCell label="Required target EBIT margin" value={formatPercent(margin)} />
      </div>
      {!converged && warnings.length ? <p className="mt-4 text-xs leading-5 text-[#FFB19D]">{warnings[0]}</p> : null}
    </div>
  )
}

function MonteCarloRange({ method, reduceMotion, progress }: { method: MethodDatum | undefined; reduceMotion: boolean; progress?: MotionValue<number> }) {
  const fallbackProgress = useMotionValue(1)
  const motionProgress = progress ?? fallbackProgress
  const rangeScale = useTransform(motionProgress, [0.53, 0.64], [0, 1])
  const medianScale = useTransform(motionProgress, [0.49, 0.56], [0, 1])
  const valueOpacity = useTransform(motionProgress, [0.48, 0.57], [0.35, 1])

  if (!method || method.low === null || method.median === null || method.high === null) {
    return <div className="mt-5 border-y border-white/12 py-5 text-sm text-[#A9A9A2]">Monte Carlo percentiles are unavailable in this response.</div>
  }

  const min = method.low
  const span = method.high - method.low || 1
  const medianPosition = Math.min(100, Math.max(0, ((method.median - min) / span) * 100))

  return (
    <div className="mt-5 border-y border-white/12 py-5">
      <motion.div className="grid grid-cols-3 gap-3" style={reduceMotion ? undefined : { opacity: valueOpacity }}>
        <MonteCarloValue label="P10 · Bear" value={method.low} />
        <MonteCarloValue label="P50 · Base" value={method.median} emphasized />
        <MonteCarloValue label="P90 · Bull" value={method.high} align="right" />
      </motion.div>
      <div className="relative mt-5 h-8" aria-label={`Monte Carlo range from ${formatMoney(method.low)} to ${formatMoney(method.high)}, median ${formatMoney(method.median)}`}>
        <div className="absolute inset-x-0 top-1/2 h-px bg-white/16" />
        <motion.div
          className="absolute inset-x-0 top-1/2 h-2 origin-center -translate-y-1/2 bg-[#B7FF3C]/28"
          style={reduceMotion ? undefined : { scaleX: rangeScale }}
        />
        <motion.span
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 bg-[#F2F2EE]"
          style={{ left: `${medianPosition}%`, ...(reduceMotion ? {} : { scale: medianScale }) }}
        />
        <span className="absolute left-0 top-1/2 h-4 w-px -translate-y-1/2 bg-[#B7FF3C]" />
        <span className="absolute right-0 top-1/2 h-4 w-px -translate-y-1/2 bg-[#B7FF3C]" />
      </div>
    </div>
  )
}

function MonteCarloValue({ label, value, emphasized = false, align = "left" }: { label: string; value: number; emphasized?: boolean; align?: "left" | "right" }) {
  return <div className={align === "right" ? "text-right" : emphasized ? "text-center" : "text-left"}><p className={`text-[0.68rem] ${emphasized ? "text-[#B7FF3C]" : "text-[#A9A9A2]"}`}>{label}</p><p className="mt-1 font-mono text-sm font-semibold text-[#F2F2EE]">{formatMoney(value)}</p></div>
}

function ValuationPlot({ methods, currentPrice, compact = false, reduceMotion = false, progress }: { methods: MethodDatum[]; currentPrice: number | null; compact?: boolean; reduceMotion?: boolean; progress?: MotionValue<number> }) {
  const fallbackProgress = useMotionValue(1)
  const motionProgress = progress ?? fallbackProgress
  const plotReveal = useTransform(motionProgress, [0.57, 0.7], ["inset(0 100% 0 0)", "inset(0 0% 0 0)"])
  const priceScale = useTransform(motionProgress, [0.78, 0.88], [0, 1])
  const values = methods.flatMap((method) => [method.value, method.low, method.high]).filter((value): value is number => value !== null && value > 0)
  if (currentPrice !== null && currentPrice > 0) values.push(currentPrice)
  if (!values.length) return <p className="mt-10 border-y border-white/12 py-12 text-sm text-[#A9A9A2]">No engine returned a valid fair value. The plot remains empty.</p>
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const padding = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.05)
  const min = Math.max(0, rawMin - padding)
  const max = rawMax + padding
  const positionPercent = (value: number) => Math.min(100, Math.max(0, ((value - min) / (max - min || 1)) * 100))
  const position = (value: number) => `${positionPercent(value)}%`
  const currentPricePosition = currentPrice !== null ? positionPercent(currentPrice) : null
  const priceLabelTransform = currentPricePosition === null
    ? "translateX(-50%)"
    : currentPricePosition <= 12
      ? "translateX(0)"
      : currentPricePosition >= 88
        ? "translateX(-100%)"
        : "translateX(-50%)"

  return (
    <figure className={`mt-7 ${compact ? "space-y-2" : "space-y-3"}`} aria-label={`Fair value plot from ${formatMoney(min)} to ${formatMoney(max)}`}>
      <div className="flex justify-between font-mono text-[0.7rem] text-[#A9A9A2]"><span>{formatMoney(min)}</span><span>USD / share</span><span data-testid="valuation-plot-max-label">{formatMoney(max)}</span></div>
      {currentPricePosition !== null ? (
        <div className="relative h-5 border-x border-white/16" aria-hidden="true">
          <span
            className="absolute top-0 whitespace-nowrap bg-[#0D0D0C] px-1 font-mono text-[0.65rem] text-[#B7FF3C]"
            style={{ left: `${currentPricePosition}%`, transform: priceLabelTransform }}
            data-testid="valuation-plot-price-label"
          >
            PRICE
          </span>
        </div>
      ) : null}
      <motion.div className="relative border-x border-white/16" style={!reduceMotion && currentPrice === null ? { clipPath: plotReveal } : undefined}>
        {currentPrice !== null ? <motion.div className="absolute inset-y-0 z-20 w-px origin-top bg-[#B7FF3C]" style={{ left: position(currentPrice), ...(reduceMotion ? {} : { scaleY: priceScale }) }} /> : null}
        {methods.map((method, index) => (
          <div key={method.key} className={`grid grid-cols-[7.5rem_1fr] items-center gap-3 border-b border-white/10 last:border-b-0 ${compact ? "min-h-9" : "min-h-11"}`}>
            <span className="truncate text-xs text-[#BDBDB6]">{method.label}</span>
            <div className="relative h-full border-l border-white/8">
              {method.value !== null ? (
                <>
                  {method.low !== null && method.high !== null ? <motion.div className="absolute top-1/2 h-1 origin-left -translate-y-1/2 bg-[#B7FF3C]/30" style={{ left: position(method.low), width: `calc(${position(method.high)} - ${position(method.low)})` }} initial={reduceMotion ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: reduceMotion ? 0 : 0.38, delay: reduceMotion ? 0 : index * 0.035, ease: [0.22, 1, 0.36, 1] }} /> : null}
                  <motion.span className="absolute top-1/2 z-10 size-2 -translate-x-1/2 -translate-y-1/2 bg-[#F2F2EE]" style={{ left: position(method.value) }} title={`${method.label}: ${formatMoney(method.value)}`} initial={reduceMotion ? false : { scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: reduceMotion ? 0 : 0.28, delay: reduceMotion ? 0 : 0.08 + index * 0.04, ease: [0.22, 1, 0.36, 1] }} />
                  {!compact ? <span className="absolute top-1/2 -translate-y-1/2 pl-2 font-mono text-[0.68rem] text-[#D8D8D0]" style={{ left: position(method.value) }}>{formatMoney(method.value)}</span> : null}
                </>
              ) : <span className="absolute inset-y-0 left-0 flex items-center text-[0.7rem] text-[#8F8F89]">{method.status.replaceAll("_", " ")}</span>}
            </div>
          </div>
        ))}
      </motion.div>
      <figcaption className="text-[0.7rem] leading-5 text-[#8F8F89]">Points are returned fair values. The DCF interval, when available, is its Monte Carlo P10–P90 range.</figcaption>
    </figure>
  )
}

function StateHeading({ title, copy }: { title: string; copy: string }) {
  return <div><h3 className="text-xl font-semibold text-[#F2F2EE]">{title}</h3><p className="mt-2 max-w-xl text-sm leading-6 text-[#A9A9A2]">{copy}</p></div>
}

function EvidenceCell({ label, value }: { label: string; value: string }) {
  return <div className="min-h-24 bg-[#0D0D0C] p-4"><p className="text-xs text-[#A9A9A2]">{label}</p><p className="mt-3 text-sm font-semibold text-[#F2F2EE]">{value}</p></div>
}

function ExpectationCell({ label, value }: { label: string; value: string }) {
  return <div className="bg-[#0D0D0C] p-4"><p className="text-xs text-[#A9A9A2]">{label}</p><p className="mt-2 font-mono text-sm font-semibold text-[#F2F2EE]">{value}</p></div>
}

function ReadoutInline({ label, value, align = "left" }: { label: string; value: string; align?: "left" | "right" }) {
  return <div className={`min-w-0 ${align === "right" ? "text-right" : ""}`}><span className="text-[#7F7F79]">{label}</span><span className="ml-2 truncate font-mono font-semibold text-[#D8D8D0]" title={value}>{value}</span></div>
}

function SourceLedger() {
  return (
    <div id="sources" className="border-y border-white/12 bg-[#050505]">
      <div className="mx-auto grid max-w-[90rem] gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[1fr_1fr] lg:items-end">
        <div><p className="text-sm font-semibold text-[#B7FF3C]">Evidence ledger</p><h2 className="valuator-display mt-6 max-w-[11ch] text-balance text-5xl font-semibold leading-[0.92] tracking-[-0.035em] sm:text-7xl">Trust is not a claim. It is a trail.</h2></div>
        <div>
          <p className="max-w-[38rem] text-lg leading-8 text-[#B8B8B1]">Every completed response retains its methodology, source references, assumptions, projections, and warnings. Missing inputs stop the calculation instead of becoming invented values.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href="https://www.sec.gov/edgar/search/" target="_blank" rel="noreferrer" className="valuator-source-link"><Database className="size-4" />SEC EDGAR <ArrowUpRight className="size-4" /></a>
            <a href="https://fiscaldata.treasury.gov/" target="_blank" rel="noreferrer" className="valuator-source-link"><Database className="size-4" />U.S. Treasury <ArrowUpRight className="size-4" /></a>
          </div>
        </div>
      </div>
    </div>
  )
}
