"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  FilingPoint,
  PricePoint,
  RevenueEarningsPoint,
} from "@/lib/api/types";

const axisTick = {
  fill: "#90B09E",
  fontSize: 11,
  fontFamily: "var(--font-mono)",
};

function ChartDataDisclosure({
  label,
  columns,
  rows,
}: {
  label: string;
  columns: string[];
  rows: string[][];
}) {
  return (
    <details className="mt-3 border-t border-white/10 pt-2">
      <summary className="summary-trust-control inline-flex min-h-11 cursor-pointer list-none items-center rounded-lg px-2 text-xs font-semibold text-[#B7FF3C] hover:bg-[#B7FF3C]/[0.06] hover:text-[#EFFAF4] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#B7FF3C] [&::-webkit-details-marker]:hidden">
        View {label} data
      </summary>
      <div className="summary-disclosure-panel mt-2 max-h-72 overflow-auto rounded-lg border border-[#1E293B]">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 bg-[#0B0F17] text-[#90B09E]">
            <tr>
              {columns.map((column) => (
                <th className="px-3 py-2 font-semibold" key={column} scope="col">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums text-slate-200">
            {rows.map((row, rowIndex) => (
              <tr className="border-t border-[#1E293B]/70" key={`${row[0]}-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td className="px-3 py-2" key={`${cell}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PriceTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ value?: number }>;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="summary-chart-tooltip rounded-md border border-[#1E293B] bg-[#0B0F17]/95 px-3 py-1.5 shadow-lg backdrop-blur">
      <span className="font-mono text-sm font-semibold tabular-nums text-slate-100">
        ${Number(payload[0].value).toFixed(2)}
      </span>
    </div>
  );
}

export function PriceHistoryChart({ points }: { points: PricePoint[] }) {
  const data = points
    .filter((point) => point.close !== null)
    .slice(-260)
    .map((point) => ({ label: point.date, value: point.close }));
  const values = data.map((point) => Number(point.value));
  const low = values.length ? Math.min(...values) : null;
  const high = values.length ? Math.max(...values) : null;
  const chartDescription = data.length
    ? `Sourced market-price history from ${data[0].label} to ${data.at(-1)?.label}. ${data.length} reported closing prices, ranging from $${low?.toFixed(2)} to $${high?.toFixed(2)}.`
    : "No sourced market-price history is available.";

  return (
    <div
      className="w-full"
      data-chart-state="ready"
    >
      <div className="summary-chart h-72 min-h-[288px] w-full" role="img" aria-label={chartDescription}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={1}
          initialDimension={{ width: 720, height: 288 }}
        >
          <AreaChart data={data} margin={{ top: 8, right: 0, bottom: 18, left: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22D3EE" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#22D3EE" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#1E293B" strokeOpacity={0.4} strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            axisLine={{ stroke: "#1E293B" }}
            tickLine={false}
            tick={axisTick}
            minTickGap={40}
            tickFormatter={(value) => String(value).slice(5)}
          />
          <YAxis
            domain={["dataMin - 5", "dataMax + 5"]}
            width={48}
            tick={axisTick}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `$${Math.round(Number(value))}`}
          />
          <Tooltip content={<PriceTooltip />} cursor={{ stroke: "#1E293B", strokeWidth: 1 }} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#22D3EE"
            strokeWidth={2}
            fill="url(#priceFill)"
            dot={false}
            activeDot={{ r: 3, fill: "#22D3EE", stroke: "#0B0F17", strokeWidth: 2 }}
            isAnimationActive={false}
          />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <ChartDataDisclosure
        label="price history"
        columns={["Date", "Close"]}
        rows={data.map((point) => [point.label, `$${Number(point.value).toFixed(2)}`])}
      />
    </div>
  );
}

function EpsTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value?: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="summary-chart-tooltip rounded-md border border-[#1E293B] bg-[#0B0F17]/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <p className="text-slate-400">{label}</p>
      <p className="font-mono tabular-nums text-slate-100">EPS ${Number(payload[0].value).toFixed(2)}</p>
    </div>
  );
}

function AnnualTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ dataKey?: string; name?: string; value?: number; color?: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="summary-chart-tooltip rounded-md border border-[#1E293B] bg-[#0B0F17]/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
      <p className="mb-1 text-slate-400">FY {label}</p>
      {payload.map((point) => (
        <p key={point.dataKey} className="font-mono tabular-nums" style={{ color: point.color }}>
          {point.name}: ${(Number(point.value) / 1_000_000_000).toFixed(1)}B
        </p>
      ))}
    </div>
  );
}

export function RevenueEarningsChart({
  points,
}: {
  points: RevenueEarningsPoint[];
}) {
  const data = points.slice(-5).map((point) => ({
    label: point.period,
    revenue: point.revenue,
    earnings: point.earnings,
  }));

  return (
    <div
      className="w-full"
      data-chart-state="ready"
    >
      <div className="summary-chart h-56 min-h-[220px] w-full" role="img" aria-label={`Reported annual revenue and net income in USD billions for ${data.length} fiscal periods, from ${data[0]?.label || "an unavailable period"} to ${data.at(-1)?.label || "an unavailable period"}.`}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={1}
          initialDimension={{ width: 520, height: 178 }}
        >
          <BarChart data={data} barGap={8} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#1E293B" strokeDasharray="3 3" />
          <XAxis
            dataKey="label"
            axisLine={{ stroke: "#1E293B" }}
            tickLine={false}
            tick={axisTick}
          />
          <YAxis width={52} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(value) => `$${Number(value) / 1_000_000_000}B`} />
          <Tooltip content={<AnnualTooltip />} cursor={{ fill: "#1E293B33" }} />
          <Legend
            wrapperStyle={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
            iconType="circle"
            iconSize={8}
          />
          <Bar dataKey="revenue" name="Revenue" fill="#38BDF8" radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          <Bar dataKey="earnings" name="Earnings" fill="#EFFAF4" radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartDataDisclosure
        label="annual performance"
        columns={["Fiscal period", "Revenue", "Net income"]}
        rows={data.map((point) => [
          point.label,
          `$${(Number(point.revenue) / 1_000_000_000).toFixed(2)}B`,
          point.earnings === null
            ? "Unavailable"
            : `$${(Number(point.earnings) / 1_000_000_000).toFixed(2)}B`,
        ])}
      />
    </div>
  );
}

export function EpsTrendChart({ points }: { points: FilingPoint[] }) {
  const data = points.slice(-4).map((point) => ({
    label: point.period,
    value: point.value,
  }));

  return (
    <div
      className="w-full"
      data-chart-state="ready"
    >
      <div className="summary-chart h-56 w-full" role="img" aria-label={`Reported quarterly earnings per share for ${data.length} periods, from ${data[0]?.label || "an unavailable period"} to ${data.at(-1)?.label || "an unavailable period"}.`}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={1} initialDimension={{ width: 420, height: 220 }}>
          <BarChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#1E293B" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={{ stroke: "#1E293B" }} />
          <YAxis width={52} tick={axisTick} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
          <Tooltip content={<EpsTooltip />} cursor={{ fill: "#1E293B33" }} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={44} isAnimationActive={false}>
            {data.map((point) => (
              <Cell key={point.label} fill="#38BDF8" />
            ))}
          </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ChartDataDisclosure
        label="quarterly EPS"
        columns={["Period", "EPS"]}
        rows={data.map((point) => [point.label, `$${Number(point.value).toFixed(2)}`])}
      />
    </div>
  );
}
