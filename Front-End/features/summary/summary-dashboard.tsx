"use client";

import { useMemo, useState, type ReactNode } from "react";
import { ArrowRight, CircleDollarSign, FileQuestion, Landmark, ShieldAlert, WalletCards } from "lucide-react";

import { ModuleState } from "@/components/states/module-state";
import { useLiveQuote } from "@/components/workspace/live-quote-provider";
import type {
  CompanyOverviewData,
  CustomerMixData,
  EpsTrendData,
  FinancialHighlightsData,
  KeyFactsData,
  PriceHistoryData,
  QuoteData,
  RevenueEarningsData,
  RevenueMixData,
  RevenueMixDimension,
  SummaryModule,
  SummaryResponse,
  SupplyChainData,
  ValuationMeasuresData,
} from "@/lib/api/types";
import { formatTimestamp } from "@/lib/formatting";

import { EpsTrendChart, PriceHistoryChart, RevenueEarningsChart } from "./illustrative-charts";

type MetricItem = { label: string; value: string; basis?: string };
type SourceAttribution = { label: string; url: string | null };
type PriceRange = "1D" | "5D" | "1M" | "6M" | "YTD" | "1Y" | "5Y" | "All";

const primaryPriceRanges: PriceRange[] = ["1M", "6M", "1Y", "5Y"];
const secondaryPriceRanges: PriceRange[] = ["1D", "5D", "YTD", "All"];
const revenueDimensionLabels: Record<RevenueMixDimension, string> = {
  business_segments: "Segments",
  products: "Products",
  geography: "Geography",
  end_markets: "End markets",
};
const revenueCategoryColors = ["#A78BFA", "#EFFAF4", "#90B09E", "#38BDF8", "#B7FF3C", "#22D3EE"] as const;

function moduleData<T>(module: SummaryModule | undefined | null): T | null {
  if (!module || !module.data) return null;
  return module.data as T;
}

function formatNumber(value: number | null | undefined, digits = 2, keepTrailingZeros = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const fixed = value.toFixed(digits);
  const formatted = keepTrailingZeros ? fixed : fixed.replace(/\.?0+$/, "");
  const [integer, decimal] = formatted.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimal ? `${grouped}.${decimal}` : grouped;
}

function formatCurrency(value: number | null | undefined, currency = "USD", alwaysShowSign = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const symbols: Record<string, string> = { USD: "$", TWD: "NT$" };
  const prefix = symbols[currency] ?? `${currency} `;
  const absolute = Math.abs(value);
  const sign = value < 0 ? "-" : alwaysShowSign && value > 0 ? "+" : "";
  const compact: [number, string] | null =
    absolute >= 1_000_000_000_000
      ? [absolute / 1_000_000_000_000, "T"]
      : absolute >= 1_000_000_000
        ? [absolute / 1_000_000_000, "B"]
        : absolute >= 1_000_000
          ? [absolute / 1_000_000, "M"]
          : null;
  if (compact) return `${sign}${prefix}${formatNumber(compact[0], 2, false)}${compact[1]}`;
  return `${sign}${prefix}${formatNumber(absolute, 2, true)}`;
}

function formatChange(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatNumber(Math.abs(value))}`;
}

function formatPercent(value: number | null | undefined, alreadyPercent = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const percent = alreadyPercent ? value : value * 100;
  return `${percent >= 0 ? "+" : ""}${formatNumber(percent)}%`;
}

function formatRange(low: number | null | undefined, high: number | null | undefined, currency = "USD") {
  if (low == null || high == null) return "—";
  return `${formatCurrency(low, currency)} - ${formatCurrency(high, currency)}`;
}

function formatProviderDate(value: string | number | null | undefined): string {
  if (value == null || value === "") return dataUnavailableText;
  const date = typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? new Date(`${value}T00:00:00Z`)
    : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function formatConfidence(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Confidence unavailable";
  const percent = value <= 1 ? value * 100 : value;
  return `${formatNumber(percent, 0)}% extraction confidence`;
}

function sentenceCase(value: string): string {
  const normalized = value.replaceAll("_", " ").trim().toLowerCase();
  return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : normalized;
}

function uniqueLabels(values: string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.trim().toLocaleLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function uniqueCustomerTypes(values: string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const key = value.trim().toLocaleLowerCase().replace(/s$/, "");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function filterPricePoints(points: PriceHistoryData["points"], range: PriceRange): PriceHistoryData["points"] {
  if (range === "All" || !points.length) return points;
  const latest = new Date(`${points.at(-1)?.date}T00:00:00Z`);
  const start = new Date(latest);
  if (range === "YTD") {
    start.setUTCMonth(0, 1);
  } else {
    const days = { "1D": 1, "5D": 7, "1M": 35, "6M": 190, "1Y": 370, "5Y": 365 * 5 + 7 }[range];
    start.setUTCDate(start.getUTCDate() - days);
  }
  return points.filter((point) => new Date(`${point.date}T00:00:00Z`) >= start);
}

function WorkspaceCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-white/10 bg-[#121824] p-4 sm:p-5 ${className}`}>
      {children}
    </section>
  );
}

function CardTitle({
  title,
  subtitle,
  source,
  action,
}: {
  title: string;
  subtitle?: string;
  source?: SourceAttribution | null;
  action?: ReactNode;
}) {
  const headerAction = action ?? (source ? <SourcePill source={source} /> : null);

  return (
    <div className="mb-5 flex min-w-0 flex-col items-start gap-2 sm:flex-row sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <h2 className="text-base font-semibold tracking-tight text-[#EFFAF4]">{title}</h2>
        {subtitle ? <p className="mt-1 text-[13px] leading-5 text-[#90B09E]">{subtitle}</p> : null}
      </div>
      {headerAction ? <div className="min-w-0 w-full sm:w-auto sm:max-w-[54%] sm:shrink">{headerAction}</div> : null}
    </div>
  );
}

function SourcePill({ source }: { source: SourceAttribution }) {
  return (
    <details className="group relative w-full max-w-full sm:w-auto">
      <summary className="summary-trust-control inline-flex min-h-11 max-w-full cursor-pointer list-none items-center justify-start gap-1.5 rounded-md px-1 text-left font-mono text-xs leading-5 text-[#90B09E] transition-colors hover:text-[#B7FF3C] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C] sm:justify-end sm:text-right [&::-webkit-details-marker]:hidden">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#B7FF3C]" aria-hidden />
        <span className="min-w-0 whitespace-normal">{source.label}</span>
        <span className="sr-only">Open source details</span>
      </summary>
      <div className="summary-disclosure-panel absolute left-0 z-20 mt-2 w-72 max-w-[80vw] rounded-lg border border-white/10 bg-[#0B0F17] p-3 text-left text-[13px] leading-5 text-slate-200 shadow-md sm:left-auto sm:right-0">
        <p className="break-words">{source.label}</p>
        {source.url ? (
          <a
            className="summary-trust-control mt-2 inline-flex min-h-11 items-center gap-1.5 font-semibold text-[#B7FF3C] hover:text-[#EFFAF4] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C]"
            href={source.url}
            rel="noreferrer"
            target="_blank"
          >
            Open provider record
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </a>
        ) : (
          <p className="mt-2 text-slate-400">Provider link is unavailable.</p>
        )}
      </div>
    </details>
  );
}

function SourceCoverage({ sources }: { sources: SummaryResponse["sources"] }) {
  const providers = [...new Map(sources.map((source) => [source.provider, source])).values()];

  const sourceLine = (source: SummaryResponse["sources"][number], key: string) => (
    <li className="min-w-0 text-[13px] leading-5 text-[#90B09E]" key={key}>
      {source.source_url ? (
        <a className="summary-trust-control inline-flex min-h-11 items-center font-semibold text-slate-100 hover:text-[#B7FF3C] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C]" href={source.source_url} target="_blank" rel="noreferrer">
          {source.provider}
        </a>
      ) : (
        <span className="font-semibold text-slate-100">{source.provider}</span>
      )}
      <span> · {source.source_timestamp || source.fetched_at.slice(0, 10)}</span>
    </li>
  );

  return (
    <>
      <details className="mt-4 border-y border-white/10 py-1 md:hidden">
        <summary className="summary-trust-control flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-xs font-semibold text-slate-100 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
          <span>Source coverage</span>
          <span className="font-mono font-normal text-[#90B09E]">{sources.length} source records</span>
        </summary>
        <ul className="summary-disclosure-panel grid gap-1 border-t border-white/10 py-2">{sources.map((source, index) => sourceLine(source, `${source.provider}-mobile-${index}`))}</ul>
      </details>

      <div className="mt-5 hidden items-center gap-3 border-y border-white/10 py-1 md:flex">
        <span className="font-mono text-xs font-semibold text-slate-200">Source coverage</span>
        <span className="font-mono text-xs text-[#90B09E]">
          {providers.slice(0, 3).map((source) => source.provider).join(" · ")}
          {providers.length > 3 ? ` · +${providers.length - 3} providers` : ""}
          {` · ${sources.length} timestamped records`}
        </span>
        <details className="relative ml-auto">
          <summary className="summary-trust-control inline-flex min-h-11 cursor-pointer list-none items-center rounded-md px-2 text-xs font-semibold text-[#B7FF3C] hover:bg-[#B7FF3C]/[0.06] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
            Review sources
          </summary>
          <ul className="summary-disclosure-panel absolute right-0 top-full z-20 mt-2 grid w-[min(760px,80vw)] gap-1 rounded-lg border border-white/10 bg-[#0B0F17] p-3 shadow-md sm:grid-cols-2">{sources.map((source, index) => sourceLine(source, `${source.provider}-register-${index}`))}</ul>
        </details>
      </div>
    </>
  );
}

function BasisDisclosure({ basis, label }: { basis?: string; label: string }) {
  if (!basis) return null;

  return (
    <details className="mt-1.5 text-left">
      <summary className="summary-trust-control inline-flex min-h-8 cursor-pointer list-none items-center rounded-md px-2 font-sans text-xs font-semibold text-[#B7FF3C] hover:bg-[#B7FF3C]/[0.06] hover:text-[#EFFAF4] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
        Calculation basis
        <span className="sr-only">: calculation details for {label}</span>
      </summary>
      <p className="summary-disclosure-panel mt-1 text-xs font-normal leading-5 text-slate-300">{basis}</p>
    </details>
  );
}

function FactGrid({ items, module }: { items: MetricItem[]; module: SummaryModule }) {
  return (
    <>
      <dl className="grid grid-cols-2 gap-x-5">
        {items.map((item) => (
          <div key={item.label} className="min-w-0 border-b border-white/10 py-3">
            <dt className="text-[13px] leading-tight text-[#90B09E]">{item.label}</dt>
            <dd className="mt-1 break-words font-mono text-sm tabular-nums text-slate-100">
              {item.value}
              <BasisDisclosure basis={item.basis} label={item.label} />
            </dd>
          </div>
        ))}
        {items.length % 2 ? <div className="border-b border-white/10 py-3" aria-hidden /> : null}
      </dl>
      <ModuleState module={module} compact />
    </>
  );
}

function StatList({ label, rows }: { label: string; rows: MetricItem[] }) {
  return (
    <details className="border-t border-white/10 pt-2">
      <summary className="summary-trust-control flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-2 text-sm font-semibold text-slate-200 hover:bg-white/[0.03] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
        <span>{label}</span>
        <span className="font-mono text-xs font-normal text-[#90B09E]">{rows.length} metrics</span>
      </summary>
      <dl className="summary-disclosure-panel mt-2 flex flex-col px-2 pb-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start justify-between gap-4 border-b border-[#1E293B]/50 py-2 last:border-b-0">
            <dt className="min-w-0 text-sm text-slate-400">
              {row.label}
              <BasisDisclosure basis={row.basis} label={row.label} />
            </dt>
            <dd className="text-right font-mono text-sm tabular-nums text-slate-100">{row.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function BusinessHeading() {
  return (
    <div id="business-economics" className="mb-1 flex items-center gap-4 scroll-mt-24 py-1">
      <h2 className="text-lg font-semibold tracking-tight text-[#EFFAF4]">Business economics</h2>
      <span className="h-px flex-1 bg-white/10" aria-hidden />
      <span className="font-mono text-xs text-[#90B09E]">
        Filing evidence
      </span>
    </div>
  );
}

function sourceCaption(summary: SummaryResponse, module: SummaryModule): SourceAttribution | null {
  const records = module.source_refs.map((index) => summary.sources[index]).filter(Boolean);
  if (!records.length) return null;
  const source = records[0];
  return {
    label: `${source.provider} • as of ${source.source_timestamp || source.fetched_at.slice(0, 10)}`,
    url: source.source_url,
  };
}

type SnapshotSignal = {
  label: string;
  value: string;
  detail: string;
  href: string;
  provenance: "Provider fact" | "App-derived" | "AI-assisted filing evidence";
  icon: ReactNode;
};

type EvidenceNotice = {
  title: string;
  detail: string;
  href: string;
};

function InvestmentSnapshot({
  ticker,
  signals,
  evidenceNotice,
}: {
  ticker: string;
  signals: SnapshotSignal[];
  evidenceNotice?: EvidenceNotice;
}) {
  const gridColumns = signals.length >= 4 ? "xl:grid-cols-4" : "xl:grid-cols-3";

  return (
    <section id="investment-snapshot" aria-labelledby="investment-snapshot-title" className="scroll-mt-28 border-b border-white/10 px-4 py-7 md:px-6 md:py-8">
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
        <div>
          <h2 id="investment-snapshot-title" className="text-xl font-bold tracking-tight text-[#EFFAF4]">
            {ticker} investment snapshot
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#90B09E]">
            {signals.length} sourced signals for a fast first read. Open any signal to inspect its evidence.
          </p>
        </div>
        <span className="font-mono text-xs text-[#90B09E]">No investment rating applied</span>
      </div>

      <div className={`mt-5 grid border-y border-white/10 ${gridColumns}`}>
        {signals.map((signal, index) => (
          <a
            key={signal.label}
            href={signal.href}
            className={`group min-w-0 py-5 transition-colors hover:bg-white/[0.025] focus-visible:relative focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#B7FF3C] ${index > 0 ? "border-t border-white/10 xl:border-l xl:border-t-0 xl:pl-5" : ""} ${index < signals.length - 1 ? "xl:pr-5" : ""}`}
          >
            <span className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <span className="text-[#B7FF3C]">{signal.icon}</span>
                {signal.label}
              </span>
              <span className="font-mono text-xs text-[#90B09E]">{signal.provenance}</span>
            </span>
            <strong className={`mt-4 block break-words font-mono font-semibold tabular-nums text-[#EFFAF4] ${index === 0 ? "text-2xl" : "text-xl"}`}>
              {signal.value}
            </strong>
            <span className="mt-1.5 block text-[13px] leading-5 text-[#90B09E]">{signal.detail}</span>
            <span className="summary-trust-control mt-3 inline-flex min-h-11 items-center gap-1 text-xs font-semibold text-[#B7FF3C] group-hover:text-[#EFFAF4]">
              View evidence
              <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </span>
          </a>
        ))}
      </div>
      {evidenceNotice ? (
        <a
          className="mt-3 flex min-h-11 flex-col justify-center border-b border-amber-400/20 px-1 py-2 text-amber-100 transition-colors hover:border-amber-300/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C] sm:flex-row sm:items-center sm:justify-between sm:gap-4"
          href={evidenceNotice.href}
        >
          <span>
            <strong className="text-sm font-semibold text-amber-200">{evidenceNotice.title}</strong>
            <span className="mt-0.5 block text-[13px] leading-5 text-amber-100/80">{evidenceNotice.detail}</span>
          </span>
          <span className="mt-2 inline-flex shrink-0 items-center gap-1 text-xs font-semibold text-amber-200 sm:mt-0">
            Review evidence <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </span>
        </a>
      ) : null}
    </section>
  );
}

function SummarySectionNav() {
  const sections = [
    ["Snapshot", "#investment-snapshot"],
    ["Price", "#price-history"],
    ["Business", "#business-economics"],
    ["Metrics", "#deep-statistics"],
  ] as const;

  return (
    <nav className="summary-section-nav" aria-label="Summary sections">
      <span className="summary-section-nav__label">Jump to</span>
      {sections.map(([label, href]) => (
        <a href={href} key={href}>{label}</a>
      ))}
    </nav>
  );
}

function SummaryHeader({
  summary,
  companyName,
  company,
  quote,
  currency,
  liveQuoteActive,
}: {
  summary: SummaryResponse;
  companyName: string;
  company: CompanyOverviewData | null;
  quote: QuoteData | null;
  currency: string;
  liveQuoteActive: boolean;
}) {
  const regularPrice = quote?.regularMarketPrice ?? quote?.price;
  const regularChange = quote?.change;
  const regularChangePct = quote?.regularMarketChangePercent ?? quote?.change_percent;
  const regularUp = (regularChange ?? 0) >= 0;
  const hasExtendedQuote = quote?.extendedPrice != null;
  const extendedUp = (quote?.extendedChangePercent ?? 0) >= 0;
  const extendedLabel =
    quote?.market_state === "PRE"
      ? "Pre-market"
      : quote?.market_state === "POST" || quote?.market_state === "CLOSED"
        ? "After hours"
        : "Extended session";

  return (
    <header className="border-b border-white/10 bg-[#010302]">
      <div className="mx-auto max-w-[1400px] px-4 py-5 md:px-6">
        <p className="text-[13px] text-[#90B09E]">
          {quote?.exchange || company?.exchange || "Exchange unavailable"} · Market price snapshot
          <span className="mx-1.5 text-slate-600">•</span>
          {currency}
        </p>

        <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-[#EFFAF4] md:text-[28px]">
              {companyName} ({summary.ticker})
            </h1>
          </div>
          <a
            href={`/stocks/${summary.ticker}/valuation`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md bg-[#B7FF3C] px-4 text-sm font-bold text-[#010302] transition-colors hover:bg-[#C7FF69] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C]"
          >
            Open {summary.ticker} fair value
            <ArrowRight className="h-4 w-4" aria-hidden />
          </a>
        </div>

        <div className="mt-3 border-t border-white/10" />

        <div className="mt-4 flex flex-wrap items-start gap-x-10 gap-y-4">
          <div>
            <div className={`flex items-baseline gap-3 ${liveQuoteActive ? "summary-live-quote-update" : ""}`} key={liveQuoteActive ? regularPrice : "server-quote"}>
              <span className="text-4xl font-bold tabular-nums text-slate-50">
                {formatCurrency(regularPrice, currency).replace(/^[A-Z]{3} /, "")}
              </span>
              <span className={`text-lg font-semibold tabular-nums ${regularUp ? "text-[#34D399]" : "text-[#FB7185]"}`}>
                {formatChange(regularChange)} ({formatPercent(regularChangePct, true)})
              </span>
            </div>
            <p className="mt-1.5 text-[13px] text-[#90B09E]">
              Regular session date: {formatProviderDate(quote?.latest_trading_day)} · provider date
            </p>
          </div>

          <div className={hasExtendedQuote ? "" : "hidden sm:block"}>
            <div className="flex items-baseline gap-3">
              <span className={`text-4xl font-bold tabular-nums ${hasExtendedQuote ? "text-slate-50" : "text-slate-600"}`}>
                {hasExtendedQuote ? formatCurrency(quote.extendedPrice, currency).replace(/^[A-Z]{3} /, "") : "—"}
              </span>
              <span
                className={`text-lg font-semibold tabular-nums ${
                  !hasExtendedQuote ? "text-slate-500" : extendedUp ? "text-[#34D399]" : "text-[#FB7185]"
                }`}
              >
                {hasExtendedQuote
                  ? `${formatChange(quote.extendedChange)} (${formatPercent(quote.extendedChangePercent, true)})`
                  : "not reported"}
              </span>
            </div>
            <p className="mt-1.5 text-[13px] text-[#90B09E]">
              {extendedLabel}:{" "}
              {hasExtendedQuote && quote?.extendedHoursTimestamp
                ? formatTimestamp(quote.extendedHoursTimestamp)
                : "provider unavailable"}
            </p>
          </div>
        </div>

        <SourceCoverage sources={summary.sources} />
      </div>
    </header>
  );
}

const dataUnavailableText = "time unavailable";

function RevenueMixCard({
  summary,
  module,
  mix,
  dimension,
  setDimension,
}: {
  summary: SummaryResponse;
  module: SummaryModule;
  mix: RevenueMixData | null;
  dimension?: RevenueMixDimension;
  setDimension: (dimension: RevenueMixDimension) => void;
}) {
  const dimensions = (["business_segments", "products", "geography", "end_markets"] as const).filter(
    (item) => mix?.revenue_mix[item]?.length,
  );
  const items = dimension ? mix?.revenue_mix[dimension] || [] : [];
  const periods = dimension
    ? [...(mix?.periods[dimension] || [])]
        .sort((left, right) => left.fiscal_year - right.fiscal_year)
        .slice(-2)
    : [];
  const latestYear = periods.at(-1)?.fiscal_year;
  const categoryMembers = [...new Set([
    ...items.map((item) => item.member),
    ...periods.flatMap((period) => period.items.map((item) => item.member)),
  ])];
  const categoryIndexByMember = new Map(categoryMembers.map((member, index) => [member, index]));

  return (
    <WorkspaceCard>
      <CardTitle
        title="Revenue Mix Matrix"
        subtitle={
          periods.length
            ? `Structural fiscal split · ${periods.map((period) => period.fiscal_year).join(" vs ")}`
            : "Reported structural revenue split"
        }
        source={sourceCaption(summary, module)}
      />

      {dimensions.length > 1 ? (
        <div className="mb-5 inline-flex flex-wrap gap-1 rounded-lg border border-[#1E293B] bg-[#0B0F17]/60 p-1">
          {dimensions.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setDimension(item)}
              aria-pressed={dimension === item}
              className={`summary-segment-button rounded-md px-3 text-xs transition-colors ${
                dimension === item
                  ? "bg-[#B7FF3C]/10 text-[#B7FF3C] ring-1 ring-inset ring-[#B7FF3C]/25"
                  : "text-slate-300 hover:bg-white/[0.04] hover:text-slate-100"
              }`}
            >
              {revenueDimensionLabels[item]}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex flex-col gap-4">
        {periods.length ? (
          periods.map((period) => (
            <StackedRevenueBar
              categoryIndexByMember={categoryIndexByMember}
              key={`${dimension}-${period.fiscal_year}`}
              period={period}
            />
          ))
        ) : (
          <EmptyPanel text="No reliable reported revenue segmentation." />
        )}
      </div>

      {items.length ? (
        <ul className="mt-5 flex flex-col gap-2">
          {items.slice(0, 6).map((item) => {
            const categoryIndex = categoryIndexByMember.get(item.member) ?? 0;
            return (
            <li key={item.member} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex items-center gap-2 text-slate-300">
                <span
                  className="summary-revenue-swatch inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-sm font-mono text-[10px] font-bold text-[#07110B]"
                  style={{ backgroundColor: revenueSwatch(categoryIndex) }}
                  aria-hidden="true"
                >
                  {revenueCategoryMarker(categoryIndex)}
                </span>
                {item.name}
              </span>
              <span className="flex items-center gap-3 font-mono text-xs tabular-nums">
                <span className="text-slate-500">
                  {latestYear ? `FY ${latestYear}` : "Latest"}
                </span>
                <span className="text-slate-600">→</span>
                <span className="text-slate-100">{formatNumber(item.percentage, 1)}%</span>
              </span>
            </li>
            );
          })}
        </ul>
      ) : null}
      <ModuleState module={module} compact />
    </WorkspaceCard>
  );
}

function StackedRevenueBar({
  period,
  categoryIndexByMember,
}: {
  period: RevenueMixData["periods"][RevenueMixDimension][number];
  categoryIndexByMember: Map<string, number>;
}) {
  const reported = period.items.filter((item) => Number.isFinite(item.percentage));
  const reportedTotal = reported.reduce((total, item) => total + Math.max(item.percentage, 0), 0);
  const residual = Math.max(0, 100 - reportedTotal);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-xs text-slate-500">FY {period.fiscal_year}</span>
        <span className="font-mono text-xs tabular-nums text-slate-500">
          {formatNumber(Math.min(100, reportedTotal), 1)}%
        </span>
      </div>
      <div
        className="summary-revenue-mix-bar flex h-4 w-full overflow-hidden rounded-full bg-[#0B0F17] sm:h-3"
        role="img"
        aria-label={`Fiscal year ${period.fiscal_year} revenue mix: ${reported.map((item) => `${item.name} ${formatNumber(item.percentage, 1)} percent`).join(", ")}${residual > 0 ? `, unallocated or unreported ${formatNumber(residual, 1)} percent` : ""}`}
      >
        {reported.map((item) => {
          const categoryIndex = categoryIndexByMember.get(item.member) ?? 0;
          return (
            <div
              key={`${period.fiscal_year}-${item.member}`}
              className="flex h-full items-center justify-center overflow-hidden border-r border-[#0B0F17] font-mono text-[10px] font-bold leading-none text-[#07110B] first:rounded-l-full last:border-r-0"
              style={{
                width: `${Math.max(0, item.percentage)}%`,
                backgroundColor: revenueSwatch(categoryIndex),
              }}
              title={`${revenueCategoryMarker(categoryIndex)} · ${item.name}: ${formatNumber(item.percentage, 1)}%`}
            >
              <span aria-hidden="true">{revenueCategoryMarker(categoryIndex)}</span>
            </div>
          );
        })}
        {residual > 0 ? (
          <div
            className="h-full last:rounded-r-full bg-slate-700/40"
            style={{ width: `${residual}%` }}
            title={`Unallocated or unreported: ${formatNumber(residual, 1)}%`}
          />
        ) : null}
      </div>
    </div>
  );
}

function revenueSwatch(index: number) {
  return revenueCategoryColors[index % revenueCategoryColors.length];
}

function revenueCategoryMarker(index: number) {
  return String.fromCharCode(65 + (index % revenueCategoryColors.length));
}

function reportedPerformanceMovement(data: RevenueEarningsData | null): string | null {
  if (!data || data.points.length < 2) return null;
  const [previous, latest] = data.points.slice(-2);
  if (!Number.isFinite(previous.revenue) || !Number.isFinite(latest.revenue) || previous.revenue <= 0) return null;

  const movement = (label: string, current: number, prior: number) => {
    const change = ((current - prior) / Math.abs(prior)) * 100;
    if (Math.abs(change) < 0.05) return `${label} was flat`;
    return `${label} ${change > 0 ? "rose" : "fell"} ${formatNumber(Math.abs(change), 1)}%`;
  };
  const statements = [movement("revenue", latest.revenue, previous.revenue)];
  if (
    latest.earnings != null
    && previous.earnings != null
    && Number.isFinite(latest.earnings)
    && Number.isFinite(previous.earnings)
    && previous.earnings > 0
    && latest.earnings >= 0
  ) {
    statements.push(movement("net income", latest.earnings, previous.earnings));
  }
  const fiscalLabel = (period: string) => /^FY\s/i.test(period) ? period : `FY ${period}`;
  return `${fiscalLabel(latest.period)} versus ${fiscalLabel(previous.period)}: ${statements.join("; ")}.`;
}

function EmptyPanel({ text, retry = true }: { text: string; retry?: boolean }) {
  return (
    <div
      className="flex h-full min-h-[160px] flex-col items-start justify-center rounded-lg border border-[#1E293B] bg-[#0B0F17]/40 px-4 py-5 text-sm text-slate-300"
      data-chart-state="empty"
    >
      <p>{text}</p>
      {retry ? (
        <button
          type="button"
          className="mt-3 inline-flex min-h-11 items-center rounded-lg border border-slate-600 px-3 text-xs font-semibold text-slate-100 transition-colors hover:border-slate-400 hover:bg-slate-800/70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C]"
          onClick={() => window.location.reload()}
        >
          Reload data
        </button>
      ) : null}
    </div>
  );
}

function SupplyChainCard({ summary, module, data }: { summary: SummaryResponse; module: SummaryModule; data: SupplyChainData | null }) {
  const exposure = data?.supply_chain_exposure;
  const inputs = [...new Set((exposure?.raw_material_dependencies || []).map((item) => item.material))];
  const footprint = [...new Set((exposure?.manufacturing_locations || []).map((item) => item.country))];
  const severityRank = { high: 3, medium: 2, low: 1, unknown: 0 } as const;
  const risk = [...(exposure?.risks || [])].sort((left, right) => {
    const severityDelta = severityRank[right.severity] - severityRank[left.severity];
    if (severityDelta !== 0) return severityDelta;
    const confidenceDelta = (right.confidence || 0) - (left.confidence || 0);
    if (confidenceDelta !== 0) return confidenceDelta;
    return (right.filing_date || "").localeCompare(left.filing_date || "");
  })[0];
  const riskIsComplete = risk != null && risk.severity !== "unknown" && Number.isFinite(risk.confidence);

  return (
    <WorkspaceCard className="scroll-mt-24">
      <CardTitle
        title="Supply Chain Exposure & Vulnerabilities"
        source={sourceCaption(summary, module)}
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <DisclosureQuadrant label="Inputs" items={inputs} empty="No named material" />
        <DisclosureQuadrant label="Footprint" items={footprint} empty="No location disclosed" />
      </div>

      <div className={riskIsComplete ? "mt-4 rounded-lg border border-amber-500/25 bg-amber-500/5 p-4" : "mt-4 rounded-lg border border-[#2A3B31] bg-[#0B0F17]/45 p-4"}>
        <div className="flex items-center gap-2">
          <span className={riskIsComplete ? "flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/15 text-amber-300" : "flex h-6 w-6 items-center justify-center rounded-md bg-[#90B09E]/10 text-[#A9C6B3]"}>
            {riskIsComplete ? <ShieldAlert className="h-3.5 w-3.5" aria-hidden /> : <FileQuestion className="h-3.5 w-3.5" aria-hidden />}
          </span>
          <span className={riskIsComplete ? "font-mono text-xs font-semibold text-amber-300" : "font-mono text-xs font-semibold text-[#A9C6B3]"}>
            {riskIsComplete ? "Material risk evidence" : "Evidence incomplete"}
          </span>
        </div>
        <h3 id="risk-evidence" className={riskIsComplete ? "mt-3 scroll-mt-24 text-sm font-semibold text-amber-200" : "mt-3 scroll-mt-24 text-sm font-semibold text-[#DCEBE2]"}>
          {riskIsComplete && risk ? sentenceCase(risk.type) : "The filing evidence is not complete enough for the primary snapshot"}
        </h3>
        {risk ? (
          <>
            <p className={riskIsComplete ? "mt-1 text-sm leading-6 text-amber-100/85" : "mt-1 text-sm leading-6 text-[#A9BAAF]"}>
              {sentenceCase(risk.type)} · {risk.severity === "unknown" ? "Severity unavailable" : `${sentenceCase(risk.severity)} severity`} · {formatConfidence(risk.confidence)}
            </p>
            <dl className="mt-3 grid gap-2 text-[13px] text-[#90B09E] sm:grid-cols-2">
              <div>
                <dt className="font-semibold text-amber-200/90">Filing</dt>
                <dd className="mt-0.5">{risk.source_form || "Form unavailable"} · {risk.filing_date || "date unavailable"}</dd>
              </div>
              <div>
                <dt className="font-semibold text-amber-200/90">Extraction status</dt>
                <dd className="mt-0.5">{riskIsComplete ? "Eligible for primary snapshot" : "Excluded from primary snapshot"}</dd>
              </div>
            </dl>
            <div className="mt-3 rounded-md bg-amber-400/5 px-3 py-2">
              <p className="text-xs font-semibold text-amber-200/90">Extracted filing passage</p>
              <blockquote className="mt-1 text-sm leading-relaxed text-amber-100/90">{risk.evidence}</blockquote>
              {risk.source_url ? (
                <a className="summary-trust-control mt-2 inline-flex min-h-11 items-center gap-1 text-xs font-semibold text-amber-200 hover:text-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#B7FF3C]" href={risk.source_url} target="_blank" rel="noreferrer">
                  Open filing source <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </a>
              ) : null}
            </div>
          </>
        ) : null}
      </div>

      <ModuleState module={module} compact />
    </WorkspaceCard>
  );
}

function DisclosureQuadrant({ label, items, empty }: { label: string; items: string[]; empty: string }) {
  const visible = items.filter(Boolean).slice(0, 5);
  return (
    <div className="border-t border-[#1E293B] pt-3">
      <span className="text-xs font-semibold text-slate-400">{label}</span>
      <div className="mt-3 flex flex-wrap gap-2">
        {(visible.length ? visible : [empty]).map((item) => (
          <span key={`${label}-${item}`} className="rounded-md border border-[#1E293B] bg-[#121824] px-2.5 py-1 font-mono text-xs text-slate-300">
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function CustomerMixCard({ summary, module, data }: { summary: SummaryResponse; module: SummaryModule; data: CustomerMixData | null }) {
  const mix = data?.customer_mix;
  const majorCustomers = (mix?.major_customers || []).filter((item) => item.percentage_basis === "revenue");
  const customerTypes = uniqueCustomerTypes(
    (mix?.customer_types || []).map((item) => sentenceCase(item.label || item.type)),
  );
  const endMarkets = uniqueLabels(
    (mix?.end_markets || []).map((item) => sentenceCase(item.market)),
  );
  const majorCustomerText = majorCustomers.length
    ? majorCustomers
        .slice(0, 3)
        .map((item) => `${item.name || "Unnamed customer"}${item.revenue_percentage != null ? ` ${formatNumber(item.revenue_percentage, 1)}%` : ""}`)
        .join(" · ")
    : "No >=10% revenue customer disclosed.";

  return (
    <WorkspaceCard>
      <CardTitle title="Customer Mix & End Markets" source={sourceCaption(summary, module)} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="border-t border-[#1E293B] pt-3">
          <span className="text-xs font-semibold text-slate-400">Major customer revenue</span>
          <p className="mt-3 text-sm leading-6 text-slate-300">{majorCustomerText}</p>
        </div>
        <div className="border-t border-[#1E293B] pt-3">
          <span className="text-xs font-semibold text-slate-400">Customer types</span>
          <div className="mt-3 flex flex-wrap gap-2">
            {(customerTypes.length ? customerTypes : ["Not explicitly disclosed"]).slice(0, 6).map((item) => (
              <span key={item} className="rounded-md border border-[#1E293B] bg-[#121824] px-2.5 py-1 font-mono text-xs text-slate-300">
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-[#1E293B] pt-3">
        <span className="text-xs font-semibold text-slate-400">End markets</span>
        <ul className="mt-3 divide-y divide-[#1E293B]/60">
          {(endMarkets.length ? endMarkets : ["Not explicitly disclosed"]).slice(0, 6).map((item) => (
            <li key={item} className="flex items-center gap-2 py-2 text-sm text-slate-300 first:pt-0 last:pb-0">
              <span className="h-1.5 w-1.5 rounded-full bg-[#B7FF3C]/80" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <ModuleState module={module} compact />
    </WorkspaceCard>
  );
}

export function SummaryDashboard({ summary }: { summary: SummaryResponse }) {
  const [priceRange, setPriceRange] = useState<PriceRange>("6M");
  const [priceRangeInteracted, setPriceRangeInteracted] = useState(false);
  const [revenueMixView, setRevenueMixView] = useState<RevenueMixDimension>("business_segments");
  const { data } = summary;
  const serverQuote = moduleData<QuoteData>(data.quote);
  const priceHistory = moduleData<PriceHistoryData>(data.price_history);
  const keyFacts = moduleData<KeyFactsData>(data.key_facts);
  const company = moduleData<CompanyOverviewData>(data.company_overview);
  const revenueMix = moduleData<RevenueMixData>(data.revenue_mix);
  const revenueEarnings = moduleData<RevenueEarningsData>(data.revenue_earnings);
  const valuation = moduleData<ValuationMeasuresData>(data.valuation_measures);
  const highlights = moduleData<FinancialHighlightsData>(data.financial_highlights);
  const supplyChain = moduleData<SupplyChainData>(data.supply_chain);
  const customerMix = moduleData<CustomerMixData>(data.customer_mix);
  const epsTrend = moduleData<EpsTrendData>(data.eps_trend);
  const latestPerformanceMovement = reportedPerformanceMovement(revenueEarnings);

  const live = useLiveQuote();
  const liveQuoteActive = Boolean(live.data && live.data.status !== "unavailable");
  const quote = useMemo<QuoteData | null>(() => {
    if (!serverQuote) return serverQuote;
    if (!live.data || live.data.status === "unavailable") return serverQuote;
    const liveData = live.data.data;
    return {
      ...serverQuote,
      price: liveData.price ?? serverQuote.price,
      change: liveData.change ?? serverQuote.change,
      change_percent: liveData.change_percent ?? serverQuote.change_percent,
      regularMarketPrice: liveData.price ?? serverQuote.regularMarketPrice,
      regularMarketChangePercent: liveData.change_percent ?? serverQuote.regularMarketChangePercent,
      market_state: liveData.market_state ?? serverQuote.market_state,
      extendedPrice: liveData.extended_price ?? serverQuote.extendedPrice,
      extendedChange: liveData.extended_change ?? serverQuote.extendedChange,
      extendedChangePercent: liveData.extended_change_percent ?? serverQuote.extendedChangePercent,
      extendedHoursTimestamp: liveData.extended_hours_timestamp ?? serverQuote.extendedHoursTimestamp,
    };
  }, [serverQuote, live.data]);

  const currency = quote?.currency || revenueEarnings?.currency || "USD";
  const companyName = company?.company_name || quote?.company_name || summary.ticker;
  const visiblePricePoints = filterPricePoints(priceHistory?.points || [], priceRange);
  const availableRevenueMixDimensions = (["business_segments", "products", "geography", "end_markets"] as const).filter(
    (dimension) => revenueMix?.revenue_mix[dimension]?.length,
  );
  const revenueMixDimension = availableRevenueMixDimensions.includes(revenueMixView)
    ? revenueMixView
    : availableRevenueMixDimensions[0];

  const keyFactItems: MetricItem[] = [
    { label: "Previous close", value: formatCurrency(keyFacts?.previous_close, currency) },
    { label: keyFacts?.range_label || "Day range", value: formatRange(keyFacts?.day_range.low, keyFacts?.day_range.high, currency) },
    { label: "52-week range", value: formatRange(keyFacts?.week_52_range.low, keyFacts?.week_52_range.high, currency) },
    { label: "Market cap", value: formatCurrency(keyFacts?.market_cap?.value, currency), basis: keyFacts?.market_cap?.basis },
    { label: "P/E (ttm)", value: formatNumber(keyFacts?.pe_ratio?.value), basis: keyFacts?.pe_ratio?.basis },
    { label: "EPS (ttm)", value: formatCurrency(keyFacts?.eps?.value, currency) },
    {
      label: keyFacts?.dividend_yield?.period_type === "ttm" ? "Dividend yield (TTM)" : "Dividend yield",
      value: keyFacts?.dividend_yield?.value == null ? "Not reported" : formatPercent(keyFacts.dividend_yield.value),
      basis: keyFacts?.dividend_yield?.basis,
    },
  ];

  const valuationItems: MetricItem[] = [
    { label: "Market cap", value: formatCurrency(valuation?.metrics?.market_cap?.value, currency), basis: valuation?.metrics?.market_cap?.basis },
    { label: "Enterprise value", value: formatCurrency(valuation?.metrics?.enterprise_value?.value, currency), basis: valuation?.metrics?.enterprise_value?.basis },
    { label: "Trailing P/E", value: formatNumber(valuation?.metrics?.trailing_pe?.value), basis: valuation?.metrics?.trailing_pe?.basis },
    { label: "Forward P/E", value: formatNumber(valuation?.metrics?.forward_pe?.value), basis: valuation?.metrics?.forward_pe?.basis },
    { label: "Price / sales", value: formatNumber(valuation?.metrics?.price_to_sales?.value), basis: valuation?.metrics?.price_to_sales?.basis },
    { label: "Price / book", value: formatNumber(valuation?.metrics?.price_to_book?.value), basis: valuation?.metrics?.price_to_book?.basis },
    { label: "EV / revenue", value: formatNumber(valuation?.metrics?.ev_to_revenue?.value), basis: valuation?.metrics?.ev_to_revenue?.basis },
    { label: "EV / EBITDA", value: formatNumber(valuation?.metrics?.ev_to_ebitda?.value), basis: valuation?.metrics?.ev_to_ebitda?.basis },
  ];

  const financialHighlightItems: MetricItem[] = [
    { label: "Revenue (ttm)", value: formatCurrency(highlights?.metrics?.revenue_ttm?.value, currency), basis: highlights?.metrics?.revenue_ttm?.basis },
    { label: "Profit margin", value: formatPercent(highlights?.metrics?.profit_margin?.value), basis: highlights?.metrics?.profit_margin?.basis },
    { label: "Return on assets", value: formatPercent(highlights?.metrics?.return_on_assets?.value), basis: highlights?.metrics?.return_on_assets?.basis },
    { label: "Return on equity", value: formatPercent(highlights?.metrics?.return_on_equity?.value), basis: highlights?.metrics?.return_on_equity?.basis },
    { label: "Net income", value: formatCurrency(highlights?.metrics?.net_income_to_common?.value, currency), basis: highlights?.metrics?.net_income_to_common?.basis },
    { label: "Total cash", value: formatCurrency(highlights?.metrics?.total_cash?.value, currency), basis: highlights?.metrics?.total_cash?.basis },
    {
      label: "Total debt / equity",
      value: highlights?.metrics?.total_debt_to_equity?.value != null
        ? `${formatNumber(highlights.metrics.total_debt_to_equity.value * 100, 2)}%`
        : "—",
      basis: highlights?.metrics?.total_debt_to_equity?.basis,
    },
    { label: "Levered free cash flow", value: formatCurrency(highlights?.metrics?.levered_free_cash_flow?.value, currency), basis: highlights?.metrics?.levered_free_cash_flow?.basis },
  ];

  const risk = supplyChain?.supply_chain_exposure?.risks?.[0];
  const riskHasUsableConfidence = risk != null && risk.severity !== "unknown" && Number.isFinite(risk.confidence);
  const snapshotSignals: SnapshotSignal[] = [
    {
      label: "Valuation context",
      value: valuation?.metrics?.trailing_pe?.value == null
        ? "Unavailable"
        : `${formatNumber(valuation.metrics.trailing_pe.value)}× trailing P/E`,
      detail: valuation?.metrics?.ev_to_ebitda?.value == null
        ? "EV / EBITDA is unavailable."
        : `${formatNumber(valuation.metrics.ev_to_ebitda.value)}× EV / EBITDA`,
      href: "#deep-statistics",
      provenance: "App-derived",
      icon: <CircleDollarSign className="h-4 w-4" aria-hidden />,
    },
    {
      label: "Profitability",
      value: highlights?.metrics?.profit_margin?.value == null
        ? "Unavailable"
        : `${formatNumber(highlights.metrics.profit_margin.value * 100)}% profit margin`,
      detail: highlights?.metrics?.return_on_equity?.value == null
        ? "Return on equity is unavailable."
        : `${formatNumber(highlights.metrics.return_on_equity.value * 100)}% return on equity`,
      href: "#deep-statistics",
      provenance: "App-derived",
      icon: <Landmark className="h-4 w-4" aria-hidden />,
    },
    {
      label: "Cash generation",
      value: highlights?.metrics?.levered_free_cash_flow?.value == null
        ? "Unavailable"
        : formatCurrency(highlights.metrics.levered_free_cash_flow.value, currency),
      detail: highlights?.metrics?.total_cash?.value == null
        ? "Total cash is unavailable."
        : `${formatCurrency(highlights.metrics.total_cash.value, currency)} total cash`,
      href: "#deep-statistics",
      provenance: "App-derived",
      icon: <WalletCards className="h-4 w-4" aria-hidden />,
    },
  ];
  if (risk && riskHasUsableConfidence) {
    snapshotSignals.push({
      label: "Material risk evidence",
      value: sentenceCase(risk.type),
      detail: `${sentenceCase(risk.severity)} severity · ${formatConfidence(risk.confidence)}`,
      href: "#risk-evidence",
      provenance: supplyChain?.extraction?.method === "ai" ? "AI-assisted filing evidence" : "Provider fact",
      icon: <ShieldAlert className="h-4 w-4" aria-hidden />,
    });
  }
  const incompleteRiskNotice: EvidenceNotice | undefined = risk && !riskHasUsableConfidence
    ? {
        title: "Risk evidence incomplete",
        detail: `${sentenceCase(risk.type)} was extracted from a filing, but ${risk.severity === "unknown" ? "severity" : "confidence"} is unavailable. It is excluded from the primary snapshot.`,
        href: "#risk-evidence",
      }
    : undefined;

  const displayWarnings = summary.warnings.filter((w) => {
    const lower = w.toLowerCase();
    return (
      !lower.includes('supabase') &&
      !lower.includes('fmp_') &&
      !lower.includes('request failed') &&
      !lower.includes('timeout')
    );
  });

  return (
    <main className="min-h-screen bg-[#0B0F17] text-slate-100">
      <SummaryHeader summary={summary} companyName={companyName} company={company} quote={quote} currency={currency} liveQuoteActive={liveQuoteActive} />

      <div className="mx-auto max-w-[1400px]">
        {displayWarnings.length ? (
          <details className="mx-4 mt-5 rounded-lg border border-[#2A3B31] bg-[#0B0F17]/55 px-3 py-2 text-sm text-[#A9BAAF] md:mx-6">
            <summary className="summary-trust-control flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 font-semibold text-[#DCEBE2] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
              <span>Coverage notes</span>
              <span className="font-mono text-xs font-normal text-[#90B09E]">{displayWarnings.length} {displayWarnings.length === 1 ? "note" : "notes"}</span>
            </summary>
            <ul className="space-y-2 border-t border-[#2A3B31] py-3 text-sm leading-6 text-[#A9BAAF]">
              {displayWarnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}
            </ul>
          </details>
        ) : null}

        <InvestmentSnapshot ticker={summary.ticker} signals={snapshotSignals} evidenceNotice={incompleteRiskNotice} />
        <SummarySectionNav />

        <div className="grid grid-cols-1 gap-6 p-4 md:p-6 lg:grid-cols-3">
          <div className="order-2 flex flex-col gap-6 lg:order-1 lg:col-span-2">
            <WorkspaceCard className="scroll-mt-24">
              <CardTitle
                title="Price History"
                subtitle={priceHistory?.interval === "daily" ? "Daily market price" : "Weekly market price"}
                source={sourceCaption(summary, data.price_history)}
              />
              <div id="price-history" className="mb-5 scroll-mt-28">
                <div className="inline-flex flex-wrap gap-1 rounded-lg border border-[#1E293B] bg-[#0B0F17]/60 p-1">
                  {primaryPriceRanges.map((range) => (
                      <button
                        key={range}
                        type="button"
                        onClick={() => {
                          setPriceRangeInteracted(true);
                          setPriceRange(range);
                        }}
                        aria-pressed={priceRange === range}
                        className={`summary-segment-button rounded-md px-3 font-mono text-xs tabular-nums transition-colors ${
                          priceRange === range
                            ? "bg-[#B7FF3C]/10 text-[#B7FF3C] ring-1 ring-inset ring-[#B7FF3C]/25"
                            : "text-slate-300 hover:bg-white/[0.04] hover:text-slate-100"
                        }`}
                      >
                        {range}
                      </button>
                  ))}
                  <label className="sr-only" htmlFor="additional-price-range">Additional price ranges</label>
                  <select
                    id="additional-price-range"
                    aria-label="Additional price ranges"
                    className="summary-segment-button min-w-24 rounded-md border-0 bg-[#121824] px-2 font-mono text-xs text-slate-200 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C]"
                    value={secondaryPriceRanges.includes(priceRange) ? priceRange : ""}
                    onChange={(event) => {
                      if (event.target.value) {
                        setPriceRangeInteracted(true);
                        setPriceRange(event.target.value as PriceRange);
                      }
                    }}
                  >
                    <option value="">More ranges</option>
                    {secondaryPriceRanges.map((range) => {
                      const disabled = priceHistory?.interval !== "daily" && (range === "1D" || range === "5D");
                      return <option disabled={disabled} key={range} value={range}>{range}</option>;
                    })}
                  </select>
                </div>
                {priceHistory?.interval !== "daily" ? (
                  <p className="mt-2 text-[13px] leading-5 text-[#90B09E]">1D and 5D ranges require daily price history from the provider.</p>
                ) : null}
              </div>
              <div className={priceRangeInteracted ? "summary-chart-range-transition" : ""} data-testid="price-history-chart" key={priceRange}>
                {visiblePricePoints.length ? (
                  <PriceHistoryChart points={visiblePricePoints} />
                ) : (
                  <EmptyPanel text="Price history is unavailable from the current provider." />
                )}
              </div>
              <ModuleState module={data.price_history} compact />
            </WorkspaceCard>

            <div className="flex flex-col gap-6">
              <BusinessHeading />
              <RevenueMixCard
                summary={summary}
                module={data.revenue_mix}
                mix={revenueMix}
                dimension={revenueMixDimension}
                setDimension={setRevenueMixView}
              />
              <SupplyChainCard summary={summary} module={data.supply_chain} data={supplyChain} />
              <CustomerMixCard summary={summary} module={data.customer_mix} data={customerMix} />
            </div>

            <WorkspaceCard className="scroll-mt-24">
              <CardTitle title="Market & Fundamentals Performance" source={sourceCaption(summary, data.revenue_earnings)} />
              <div id="market-performance" className="grid scroll-mt-24 grid-cols-1 gap-8 xl:grid-cols-2">
                <div>
                  <h3 className="mb-4 text-sm font-semibold text-slate-200">Reported quarterly EPS</h3>
                  <div data-testid="eps-trend-chart">
                    {epsTrend?.points.length ? <EpsTrendChart points={epsTrend.points} /> : <EmptyPanel text="Reported quarterly EPS is unavailable." />}
                  </div>
                  <ModuleState module={data.eps_trend} compact />
                </div>
                <div>
                  <h3 className="mb-4 text-sm font-semibold text-slate-200">Annual revenue vs. earnings</h3>
                  <div data-testid="revenue-earnings-chart">
                    {revenueEarnings?.points.length ? (
                      <RevenueEarningsChart points={revenueEarnings.points} />
                    ) : (
                      <EmptyPanel text="Annual revenue and earnings history is unavailable." />
                    )}
                  </div>
                  <ModuleState module={data.revenue_earnings} compact />
                </div>
              </div>
              {latestPerformanceMovement ? (
                <p className="mt-5 border-t border-[#1E293B] pt-4 text-[13px] leading-5 text-slate-300">
                  <span className="mr-2 font-semibold text-[#A78BFA]">Latest reported movement</span>
                  <span>{latestPerformanceMovement}</span>
                </p>
              ) : null}
            </WorkspaceCard>
          </div>

          <aside className="contents lg:order-2 lg:flex lg:flex-col lg:gap-6">
            <WorkspaceCard className="order-1 scroll-mt-24">
              <div id="key-facts" className="scroll-mt-24" />
              <CardTitle title="Key Facts" source={sourceCaption(summary, data.key_facts)} />
              <FactGrid items={keyFactItems} module={data.key_facts} />
            </WorkspaceCard>

            <WorkspaceCard className="summary-sticky-rail order-3 scroll-mt-24 lg:sticky">
              <div id="deep-statistics" className="scroll-mt-24" />
              <CardTitle title="Valuation & quality metrics" subtitle="Expand a group to inspect calculation basis" source={sourceCaption(summary, data.valuation_measures)} />
              <div className="flex flex-col gap-3">
                <StatList label="Valuation measures" rows={valuationItems} />
                <StatList label="Financial highlights" rows={financialHighlightItems} />
              </div>
              <ModuleState module={data.valuation_measures} compact />
              <ModuleState module={data.financial_highlights} compact />
            </WorkspaceCard>
          </aside>
        </div>

        <footer className="border-t border-[#1E293B] px-4 py-5 md:px-6">
          <p className="font-mono text-xs leading-relaxed text-[#90B09E]">
            Source-aware workspace. Figures retain provider source references and are not investment advice.
          </p>
        </footer>
      </div>
    </main>
  );
}
