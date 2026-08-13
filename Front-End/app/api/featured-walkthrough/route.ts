import { NextResponse } from "next/server"
import { consumeRateLimit, rateLimitHeaders } from "@/lib/security/rate-limit"

const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8200"

const FEATURED_TICKER = (process.env.FEATURED_TICKER ?? "MSFT").toUpperCase()
const REVALIDATE_SECONDS = 3600

const enginePaths = {
  asset: "asset-based",
  dcf: "dcf",
  ddm: "ddm",
  relative: "relative",
  residual: "residual-income",
} as const

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

async function fetchJson(path: string): Promise<JsonRecord> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    next: { revalidate: REVALIDATE_SECONDS },
    signal: AbortSignal.timeout(90000),
  })

  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isRecord(payload)) {
    throw new Error(`${path} returned an invalid payload`)
  }
  return payload
}

function nestedRecord(parent: JsonRecord | undefined, key: string) {
  const value = parent?.[key]
  return isRecord(value) ? value : undefined
}

function collectTelemetrySources(engines: Record<string, JsonRecord | null>) {
  const sources = new Set<string>()

  Object.values(engines).forEach((engine) => {
    const assumptions = nestedRecord(engine ?? undefined, "underlying_assumptions")
    const telemetry = nestedRecord(assumptions, "telemetry")
    ;[assumptions, telemetry].forEach((record) => {
      if (!record) return
      Object.entries(record).forEach(([key, value]) => {
        if (key.endsWith("_source") && typeof value === "string" && value.trim()) {
          sources.add(value.trim())
        }
      })
    })
  })

  return [...sources]
}

export const dynamic = "force-dynamic"

export async function GET(request: Request) {
  const rateLimit = consumeRateLimit(request, "featured-walkthrough", 30)
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { detail: { code: "rate_limited", message: "Too many requests.", retry_after_seconds: rateLimit.retryAfter } },
      { status: 429, headers: { ...rateLimitHeaders(rateLimit), "Retry-After": String(rateLimit.retryAfter) } },
    )
  }
  const requests = Object.entries(enginePaths).map(async ([key, path]) => {
    const payload = await fetchJson(`/api/v1/valuation/${path}?ticker=${FEATURED_TICKER}`)
    return [key, payload] as const
  })

  const [summaryResult, ...engineResults] = await Promise.allSettled([
    fetchJson(`/api/stocks/${FEATURED_TICKER}/summary`),
    ...requests,
  ])

  const engines: Record<string, JsonRecord | null> = Object.fromEntries(
    Object.keys(enginePaths).map((key) => [key, null]),
  )
  const warnings: string[] = []

  engineResults.forEach((result, index) => {
    const engineKey = Object.keys(enginePaths)[index]
    if (result.status === "fulfilled") {
      const [key, payload] = result.value
      engines[key] = payload
    } else {
      warnings.push(`${engineKey}: ${result.reason instanceof Error ? result.reason.message : "unavailable"}`)
    }
  })

  const summary = summaryResult.status === "fulfilled" ? summaryResult.value : null
  if (summaryResult.status === "rejected") {
    warnings.push(`summary: ${summaryResult.reason instanceof Error ? summaryResult.reason.message : "unavailable"}`)
  }

  const summaryData = nestedRecord(summary ?? undefined, "data")
  const overviewModule = nestedRecord(summaryData, "company_overview")
  const overview = nestedRecord(overviewModule, "data")
  const companyName = typeof overview?.company_name === "string" ? overview.company_name : null

  const summarySources = Array.isArray(summary?.sources)
    ? summary.sources
        .filter(isRecord)
        .map((source) => source.provider)
        .filter((provider): provider is string => typeof provider === "string" && Boolean(provider.trim()))
    : []

  const providers = [...new Set([...summarySources, ...collectTelemetrySources(engines)])]
  const completedEngines = Object.values(engines).filter(Boolean).length

  return NextResponse.json(
    {
      ticker: FEATURED_TICKER,
      company_name: companyName,
      fetched_at: new Date().toISOString(),
      cache_ttl_seconds: REVALIDATE_SECONDS,
      status: completedEngines > 0 ? (completedEngines === 5 ? "complete" : "partial") : "unavailable",
      providers,
      engines,
      warnings,
    },
    {
      headers: {
        "Cache-Control": `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate=86400`,
        ...rateLimitHeaders(rateLimit),
      },
    },
  )
}
