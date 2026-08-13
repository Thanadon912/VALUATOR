import { notFound } from "next/navigation";

import { ValuationDashboard } from "@/features/valuation/valuation-dashboard";
import { normalizeTicker } from "@/lib/validation/ticker";

export const dynamic = "force-dynamic";

export default async function ValuationPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const normalized = normalizeTicker(ticker);

  if (!normalized) {
    notFound();
  }

  return <ValuationDashboard ticker={normalized} />;
}
