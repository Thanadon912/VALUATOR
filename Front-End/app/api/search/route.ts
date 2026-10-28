import { NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { normalizeTicker } from "@/lib/validation/ticker";
import {
  consumeRateLimit,
  rateLimitHeaders,
  tryAcquireCapacity,
} from "@/lib/security/rate-limit";

const API_BASE_URL = process.env.API_BASE_URL ?? "http://127.0.0.1:8200";
const COMPANY_SEARCH_UNAVAILABLE =
  "Company-name search is temporarily unavailable. Enter a ticker symbol such as AAPL or BRK.B.";

// Pre-populated verified tickers (S&P 500 / NASDAQ top traded US equities)
const PREPOPULATED_TICKERS = [
  "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
  "BRK.A", "BRK.B", "JPM", "V", "UNH", "WMT", "XOM", "MA", "JNJ",
  "PG", "HD", "COST", "ABBV", "BAC", "CRM", "NFLX", "AMD", "ORCL",
  "ADBE", "CVX", "KO", "PEP", "TMO", "LIN", "ACN", "CSCO", "MCD",
  "DIS", "ABT", "GE", "INTC", "QCOM", "TXN", "CAT", "VZ", "IBM",
  "AMAT", "NOW", "UBER", "PFE", "NKE", "PLTR", "TSM", "ASML",
  "AVGO", "LLY", "MRK", "WFC", "MS", "GS", "SPGI", "BLK", "RTX",
  "HON", "BA", "LMT", "COP", "SLB", "EOG", "PXD", "NEE", "SO",
  "DUK", "ISRG", "SYK", "MDT", "GILD", "AMGN", "VRTX", "REGN",
  "BKNG", "TJX", "SBUX", "LOW", "MDLZ", "T", "CMCSA", "PANW",
  "SNPS", "CDNS", "CRWD", "FTNT", "MDB", "SNOW", "DDOG", "COIN",
  "HOOD", "SQ", "PYPL", "SHOP", "SE", "BABA", "PDD", "JD", "RKLB",
  "COKE", "F", "SPCX",
];

// Pre-populated common company name -> ticker mappings
const PREPOPULATED_ALIASES: Record<string, string> = {
  "meta": "META",
  "meta platforms": "META",
  "facebook": "META",
  "fb": "META",
  "apple": "AAPL",
  "apple inc": "AAPL",
  "microsoft": "MSFT",
  "google": "GOOGL",
  "alphabet": "GOOGL",
  "amazon": "AMZN",
  "nvidia": "NVDA",
  "tesla": "TSLA",
  "berkshire": "BRK.B",
  "berkshire hathaway": "BRK.B",
  "netflix": "NFLX",
  "palantir": "PLTR",
  "tsmc": "TSM",
  "taiwan semiconductor": "TSM",
  "asml": "ASML",
  "broadcom": "AVGO",
  "eli lilly": "LLY",
  "jpmorgan": "JPM",
  "jp morgan": "JPM",
  "visa": "V",
  "walmart": "WMT",
  "exxon": "XOM",
  "mastercard": "MA",
  "johnson & johnson": "JNJ",
  "johnson and johnson": "JNJ",
  "procter & gamble": "PG",
  "home depot": "HD",
  "costco": "COST",
  "coca cola": "KO",
  "coca-cola": "KO",
  "ford": "F",
  "gm": "GM",
  "general motors": "GM",
  "pepsi": "PEP",
  "disney": "DIS",
  "walt disney": "DIS",
  "intel": "INTC",
  "amd": "AMD",
  "qualcomm": "QCOM",
  "boeing": "BA",
  "crowdstrike": "CRWD",
  "uber": "UBER",
  "coinbase": "COIN",
  "robinhood": "HOOD",
  "paypal": "PYPL",
  "shopify": "SHOP",
  "alibaba": "BABA",
  "spacex": "SPCX",
  "space exploration technologies": "SPCX",
  "space exploration technologies corp": "SPCX",
};

// In-Memory Ticker Cache
const queryCache = new Map<string, string>();
const verifiedTickers = new Set<string>(PREPOPULATED_TICKERS);

// Initialize query cache with direct verified tickers first
for (const ticker of PREPOPULATED_TICKERS) {
  verifiedTickers.add(ticker);
  queryCache.set(ticker.toLowerCase(), ticker);
  queryCache.set(ticker, ticker);
}

// Then seed company name aliases (names with spaces or >5 chars).
// Aliases of <= 5 chars (like "ford") are verified against the ticker candidate engine first
// so that real tickers (like NASDAQ: COKE) are never accidentally overridden by an alias.
for (const [name, sym] of Object.entries(PREPOPULATED_ALIASES)) {
  const normName = name.toLowerCase().trim();
  const squished = normName.replace(/\s+/g, "");
  const isCandidate =
    /^[a-z]{1,5}$/.test(squished) ||
    (/^[a-z0-9.-]{1,7}$/.test(squished) && (squished.includes(".") || squished.includes("-")));
  if (!isCandidate && !verifiedTickers.has(normName.toUpperCase())) {
    queryCache.set(normName, sym);
  }
}

export async function GET(request: Request) {
  const rateLimit = consumeRateLimit(request, "search", 10);
  if (!rateLimit.allowed) {
    return NextResponse.json(
      {
        detail: {
          code: "rate_limited",
          message: "Too many search requests. Try again shortly.",
          retry_after_seconds: rateLimit.retryAfter,
        },
      },
      {
        status: 429,
        headers: {
          ...rateLimitHeaders(rateLimit),
          "Retry-After": String(rateLimit.retryAfter),
        },
      },
    );
  }
  const release = tryAcquireCapacity("search", 2);
  if (!release) {
    return NextResponse.json(
      { detail: { code: "capacity_exceeded", message: "Search is busy. Try again shortly." } },
      { status: 503, headers: { ...rateLimitHeaders(rateLimit), "Retry-After": "5" } },
    );
  }

  try {
    const { searchParams } = new URL(request.url);
    const rawQuery = searchParams.get("q") ?? "";
    const query = rawQuery.trim().replace(/\s+/g, " ");

    if (!query) {
      return json({ error: "Missing query" }, rateLimit, { status: 400 });
    }
    if (query.length > 120) {
      return json({ error: "Search query is too long." }, rateLimit, { status: 422 });
    }

    const lowerQuery = query.toLowerCase();

    // 1. In-Memory Search Query Cache Check (Instant < 1ms)
    const cachedSymbol = queryCache.get(lowerQuery);
    if (cachedSymbol) {
      return json({ symbol: cachedSymbol }, rateLimit);
    }

    // 2. Direct Ticker Candidate Check
    // Standard US common stock tickers are 1-5 letters (e.g. AAPL, META, GOOGL),
    // or rare share-class symbols with a dot/hyphen (e.g. BRK.B).
    // Words longer than 5 letters without dot/hyphen (e.g. "FERRARI", "BOEING", "MICROSOFT")
    // are company names, NOT ticker codes. Checking them against a ticker validation API
    // would waste an HTTP round-trip before calling AI.
    const squished = query.replace(/\s+/g, "").toUpperCase();
    const isTickerCandidate =
      /^[A-Z]{1,5}$/.test(squished) ||
      (/^[A-Z0-9.-]{1,7}$/.test(squished) && (squished.includes(".") || squished.includes("-")));

    if (isTickerCandidate) {
      const directTicker = normalizeTicker(squished);
      if (directTicker && (await isValidTicker(directTicker))) {
        queryCache.set(lowerQuery, directTicker);
        queryCache.set(directTicker.toLowerCase(), directTicker);
        return json({ symbol: directTicker }, rateLimit);
      }
    }

    // 3. Fallback: Fast Alias Check for candidate words that are not valid tickers (e.g. "ford" -> F)
    const aliasSymbol = PREPOPULATED_ALIASES[lowerQuery];
    if (aliasSymbol && (await isValidTicker(aliasSymbol))) {
      queryCache.set(lowerQuery, aliasSymbol);
      return json({ symbol: aliasSymbol }, rateLimit);
    }

    // 4. AI Resolution (Gemini AI for natural language company names)
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return searchUnavailable(rateLimit);
    }

    try {
      const genAI = new GoogleGenerativeAI(apiKey);
      const model = genAI.getGenerativeModel({
        model: "gemini-2.5-flash",
        systemInstruction:
          "You are a financial ticker routing engine. Convert the user's input into its primary US stock ticker symbol (NASDAQ or NYSE). Respond ONLY with the capitalized ticker symbol (e.g., AAPL, MSFT, META). Do not include any other words, markdown, or punctuation. If the company is not publicly traded in the US, or the input is gibberish, respond EXACTLY with the string 'NOT_FOUND'.",
        generationConfig: {
          temperature: 0.0,
        },
      });

      const result = await model.generateContent(query);
      const textResponse = result.response.text().trim();
      const symbol = normalizeTicker(textResponse);

      if (textResponse === "NOT_FOUND" || !symbol || !(await isValidTicker(symbol))) {
        return json(
          { error: "No matching US ticker found." },
          rateLimit,
          { status: 404 },
        );
      }

      // Cache the resolved result for instant future lookups
      queryCache.set(lowerQuery, symbol);
      queryCache.set(symbol.toLowerCase(), symbol);

      return json({ symbol }, rateLimit);
    } catch (error) {
      console.error("LLM search resolution failed", {
        errorType: error instanceof Error ? error.name : "UnknownError",
      });
      return searchUnavailable(rateLimit);
    }
  } finally {
    release();
  }
}

/**
 * Lightweight ticker validation decoupled from full quote fetching.
 * Does not block on multi-second Nasdaq/Alpaca quote aggregators.
 */
async function isValidTicker(ticker: string): Promise<boolean> {
  // 1. Fast in-memory check
  if (verifiedTickers.has(ticker)) {
    return true;
  }

  // 2. Fast backend validation endpoint
  try {
    const validateRes = await fetch(`${API_BASE_URL}/api/stocks/${ticker}/validate`, {
      cache: "no-store",
      signal: AbortSignal.timeout(1800),
    });
    if (validateRes.ok) {
      const payload = (await validateRes.json()) as { valid?: boolean };
      if (payload?.valid) {
        verifiedTickers.add(ticker);
        return true;
      }
      return false;
    }
  } catch {
    // If /validate endpoint is unreachable or times out, proceed to fallback
  }

  // 3. Fallback: lightweight quote check
  try {
    const response = await fetch(`${API_BASE_URL}/api/stocks/${ticker}/quote`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return false;

    const payload = (await response.json()) as {
      status?: unknown;
      data?: { price?: unknown; symbol?: unknown };
    };
    const isValid =
      payload.status === "success" &&
      typeof payload.data?.price === "number" &&
      normalizeTicker(String(payload.data?.symbol ?? "")) === ticker;

    if (isValid) {
      verifiedTickers.add(ticker);
    }
    return isValid;
  } catch {
    return false;
  }
}

function searchUnavailable(rateLimit: ReturnType<typeof consumeRateLimit>) {
  return json(
    { error: COMPANY_SEARCH_UNAVAILABLE },
    rateLimit,
    {
      status: 503,
      headers: { "Cache-Control": "no-store, max-age=0" },
    },
  );
}

function json(
  body: unknown,
  rateLimit: ReturnType<typeof consumeRateLimit>,
  init: ResponseInit = {},
) {
  const response = NextResponse.json(body, init);
  for (const [key, value] of Object.entries(rateLimitHeaders(rateLimit))) {
    response.headers.set(key, value);
  }
  return response;
}
