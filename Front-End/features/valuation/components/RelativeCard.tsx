import { Table2 } from "lucide-react"
import { GlassCard, CardHeading } from "@/components/ui/glass-card"
import { fmt } from "@/lib/valuation"

export interface RelativePeer {
  symbol?: string;
  name?: string;
  pe?: number | null;
  pb?: number | null;
  ev_ebitda?: number | null;
  overlap_score?: number;
  reason?: string;
  isTarget?: boolean;
}

export interface RelativeData {
  ticker: string;
  computed_fair_value: number;
  margin_of_safety_percentage: number;
  valuation_status: string;
  underlying_assumptions: {
    avg_pe?: number | null;
    avg_pb?: number | null;
    avg_ev_ebitda?: number | null;
    fv_pe?: number | null;
    fv_pb?: number | null;
    fv_ev_ebitda?: number | null;
    target_eps?: number;
    target_bvps?: number;
    target_ebitda?: number;
    target_debt?: number;
    target_cash?: number;
    shares_outstanding?: number;
    peers?: RelativePeer[];
    available_peers?: RelativePeer[];
    included_peer_symbols?: string[];
    peer_selection_basis?: "all_available_peers" | "user_selected_available_peers";
  };
  current_price: number;
}

function formatMultiple(value: number | null) {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? `${value.toFixed(1)}x`
    : "N/M"
}

export function RelativeCard({
  data,
  selectedPeerSymbols,
  isUpdating = false,
  onPeerSelectionChange,
}: {
  data: RelativeData;
  selectedPeerSymbols?: string[] | null;
  isUpdating?: boolean;
  onPeerSelectionChange?: (symbols: string[]) => void;
}) {
  const { underlying_assumptions } = data;
  const rawPeers = underlying_assumptions.available_peers?.length
    ? underlying_assumptions.available_peers
    : underlying_assumptions.peers ?? [];
  const dynamicPeers = rawPeers.map((p) => ({
    symbol: p.symbol || `Unknown`,
    name: p.name || `Unknown`,
    pe: typeof p.pe === "number" && p.pe > 0 ? p.pe : null,
    pb: typeof p.pb === "number" && p.pb > 0 ? p.pb : null,
    evEbitda: typeof p.ev_ebitda === "number" && p.ev_ebitda > 0 ? p.ev_ebitda : null,
    overlapScore: typeof p.overlap_score === "number"
      ? p.overlap_score <= 1 ? p.overlap_score * 100 : p.overlap_score
      : 0,
    reason: p.reason || "Business overlap detail unavailable",
    isTarget: p.isTarget || false
  })).sort((a, b) => b.overlapScore - a.overlapScore);
  const responseSymbols = underlying_assumptions.included_peer_symbols
    ?? underlying_assumptions.peers?.flatMap((peer) => peer.symbol ? [peer.symbol] : [])
    ?? [];
  const activeSymbols = new Set(selectedPeerSymbols ?? responseSymbols);
  const fairValue = data.computed_fair_value;
  const marginOfSafety = data.margin_of_safety_percentage;
  const isOvervalued = marginOfSafety < 0;
  const fairValueColor = isOvervalued ? "text-amber-400" : "text-[#00FF66]";

  const togglePeer = (symbol: string) => {
    if (!onPeerSelectionChange || isUpdating) return
    const next = new Set(activeSymbols)
    if (next.has(symbol)) {
      if (next.size === 1) return
      next.delete(symbol)
    } else {
      next.add(symbol)
    }
    onPeerSelectionChange(dynamicPeers.map((peer) => peer.symbol).filter((peer) => next.has(peer)))
  }

  return (
    <GlassCard aria-busy={isUpdating}>
      <CardHeading
        title="Relative Valuation"
        subtitle="Peer multiples matrix"
        icon={<Table2 className="h-4 w-4" />}
        tooltipText="Estimates fair value by comparing the company's financial multiples (e.g., P/E, P/B) against its industry peers."
        badge={
          <span role="status" className="rounded-md border border-[#1A2E20] bg-[#111613] px-2 py-1 font-mono text-xs tabular-nums text-white">
            {isUpdating
              ? "Recalculating…"
              : underlying_assumptions.avg_pe !== null && underlying_assumptions.avg_pe !== undefined
                ? `Median P/E ${underlying_assumptions.avg_pe.toFixed(1)}x`
                : "No P/E"}
          </span>
        }
      />
      <div className="p-2 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 px-2 pb-3 text-xs text-[#88998C]">
          <p>Select sourced peers to request a new backend valuation.</p>
          <p className="font-mono tabular-nums">
            {activeSymbols.size} of {dynamicPeers.length} peers included
          </p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-[#88998C]">
              <th className="w-8 px-2 py-2"></th>
              <th className="px-3 py-2 text-left font-medium">Peer Ticker</th>
              <th className="px-2 py-2 text-right font-medium">P/E</th>
              <th className="px-2 py-2 text-right font-medium">P/B</th>
              <th className="px-2 py-2 text-right font-medium">EV/EBITDA</th>
            </tr>
          </thead>
          <tbody>
            {dynamicPeers.map((peer) => (
              <tr
                key={peer.symbol}
                title={peer.reason}
                className={`border-t border-[#1A2E20] transition-colors duration-150 hover:bg-[#1A2E20]/40 ${peer.isTarget ? 'bg-[#00FF66]/10' : ''} ${activeSymbols.has(peer.symbol) ? "" : "opacity-45"}`}
              >
                <td className="p-0">
                  <label className="flex min-h-11 min-w-11 cursor-pointer items-center justify-center">
                    <input
                      type="checkbox"
                      aria-label={`Include ${peer.symbol} in peer valuation`}
                      checked={activeSymbols.has(peer.symbol)}
                      disabled={isUpdating || (activeSymbols.has(peer.symbol) && activeSymbols.size === 1)}
                      onChange={() => togglePeer(peer.symbol)}
                      className="h-3.5 w-3.5 rounded border-[#1A2E20] bg-[#111613] text-[#00FF66] focus:ring-[#00FF66] focus:ring-offset-[#0A0D0B]"
                    />
                  </label>
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-col">
                    <span className={`font-mono text-xs font-semibold ${peer.isTarget ? 'text-[#00FF66]' : 'text-white'}`}>{peer.symbol}</span>
                    <span className="mt-0.5 text-[10px] text-[#88998C]">{peer.overlapScore.toFixed(0)}% overlap</span>
                  </div>
                </td>
                <td className="px-2 py-2.5 text-right font-mono tabular-nums text-[#88998C]">
                  {formatMultiple(peer.pe)}
                </td>
                <td className="px-2 py-2.5 text-right font-mono tabular-nums text-[#88998C]">
                  {formatMultiple(peer.pb)}
                </td>
                <td className="px-2 py-2.5 text-right font-mono tabular-nums text-[#88998C]">
                  {formatMultiple(peer.evEbitda)}
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-[#1A2E20] bg-[#0A0D0B]">
              <td className="px-3 py-3 text-xs font-bold text-white" colSpan={3}>Backend Blended Fair Value</td>
              <td className={`px-2 py-3 text-right font-mono text-xs font-semibold ${fairValueColor}`}>
                {marginOfSafety >= 0 ? "+" : ""}{marginOfSafety.toFixed(1)}%
              </td>
              <td className={`px-2 py-3 text-right font-mono font-bold ${fairValueColor}`}>
                ${fmt.money(fairValue)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </GlassCard>
  )
}
