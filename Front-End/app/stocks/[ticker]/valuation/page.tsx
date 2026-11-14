import { notFound } from "next/navigation";

import { ValuationDashboard } from "@/features/valuation/valuation-dashboard";
import { normalizeTicker } from "@/lib/validation/ticker";

export const dynamic = "force-dynamic";

export default async function ValuationPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams?: Promise<{ tab?: string }>;
}) {
  const { ticker } = await params;
  const resolvedSearchParams = searchParams ? await searchParams : undefined;
  const normalized = normalizeTicker(ticker);

  if (!normalized) {
    notFound();
  }

  const rawTab = resolvedSearchParams?.tab;
  const initialTab = rawTab === "dcf" || rawTab === "sim" || rawTab === "overview" ? rawTab : "overview";

  return <ValuationDashboard ticker={normalized} initialTab={initialTab} />;
}
