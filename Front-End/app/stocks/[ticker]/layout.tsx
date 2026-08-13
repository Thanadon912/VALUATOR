import { LiveQuoteProvider } from "@/components/workspace/live-quote-provider";
import { WorkspaceTopbar } from "@/components/workspace/workspace-topbar";
import { getLiveQuote } from "@/lib/api/quote";

export default async function StockLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const normalized = ticker.trim().toUpperCase();

  // Seed the workspace-wide SWR stream once (Bucket B). This initial fetch
  // is the only server-side quote call; every page then shares one
  // client-driven live stream from here. A backend failure degrades to an
  // `unavailable` seed so the structural workspace still renders.
  const seedQuote = await getLiveQuote(normalized);

  return (
    <LiveQuoteProvider ticker={normalized} fallback={seedQuote}>
      <div className="workspace">
        <a className="workspace-skip-link" href="#stock-workspace-content">
          Skip to company analysis
        </a>
        <WorkspaceTopbar ticker={normalized} />
        <div className="workspace__main">
          <div id="stock-workspace-content">{children}</div>
        </div>
      </div>
    </LiveQuoteProvider>
  );
}
