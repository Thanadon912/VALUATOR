import { notFound } from "next/navigation";
import { NewsSignals } from "@/features/news/NewsSignals";
import { normalizeTicker } from "@/lib/validation/ticker";

export const dynamic = "force-dynamic";

export default async function NewsPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const normalized = normalizeTicker(ticker);

  if (!normalized) {
    notFound();
  }

  return <NewsSignals ticker={normalized} />;
}
