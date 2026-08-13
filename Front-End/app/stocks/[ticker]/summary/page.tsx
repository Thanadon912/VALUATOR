import { notFound } from "next/navigation";

import { SummaryDashboard } from "@/features/summary/summary-dashboard";
import { getSummary } from "@/lib/api/summary";
import { normalizeTicker } from "@/lib/validation/ticker";

export const dynamic = "force-dynamic";

export default async function SummaryPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const normalized = normalizeTicker(ticker);

  if (!normalized) {
    notFound();
  }

  const summary = await getSummary(normalized);

  return <SummaryDashboard summary={summary} />;
}
