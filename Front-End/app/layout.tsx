import type { Metadata } from "next";

import { listSavedStocks } from "@/features/saved-stocks/actions";
import { SavedStocksProvider } from "@/features/saved-stocks/saved-stocks-provider";
import { listValuationAssumptions } from "@/features/valuation-assumptions/actions";
import { ValuationAssumptionsProvider } from "@/features/valuation-assumptions/valuation-assumptions-provider";
import { ReleaseFreshness } from "@/components/release-freshness";

import "./globals.css";

export const metadata: Metadata = {
  title: "VALUATOR — Market Expectations, Made Visible",
  description: "Trace market expectations through sourced evidence, explicit assumptions, and five valuation methods.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const [savedStocks, valuationAssumptions] = await Promise.all([
    listSavedStocks(),
    listValuationAssumptions(),
  ]);
  const initialSavedStocks = savedStocks.ok ? savedStocks.data : null;
  const initialValuationAssumptions = valuationAssumptions.ok
    ? valuationAssumptions.data
    : null;

  return (
    <html lang="en">
      <body>
        <ReleaseFreshness
          currentRevision={
            process.env.VERCEL_GIT_COMMIT_SHA ??
            process.env.APP_REVISION ??
            "development"
          }
        />
        <SavedStocksProvider initialSession={initialSavedStocks}>
          <ValuationAssumptionsProvider initialSession={initialValuationAssumptions}>
            {children}
          </ValuationAssumptionsProvider>
        </SavedStocksProvider>
      </body>
    </html>
  );
}
