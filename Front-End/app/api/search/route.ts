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
    const query = searchParams.get("q")?.trim();

  if (!query) {
    return json({ error: "Missing query" }, rateLimit, { status: 400 });
  }
  if (query.length > 120) {
    return json({ error: "Search query is too long." }, rateLimit, { status: 422 });
  }

  const directTicker = normalizeTicker(query);
  if (directTicker && await hasLiveQuote(directTicker)) {
    return json({ symbol: directTicker }, rateLimit);
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return searchUnavailable(rateLimit);
  }

  try {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({
      model: "gemini-3.1-flash-lite",
      systemInstruction:
        "You are a financial ticker routing engine. Convert the user's input into its primary US stock ticker symbol (NASDAQ or NYSE). Respond ONLY with the capitalized ticker symbol (e.g., AAPL, MSFT, META). Do not include any other words, markdown, or punctuation. If the company is not publicly traded in the US, or the input is gibberish, respond EXACTLY with the string 'NOT_FOUND'.",
      generationConfig: {
        temperature: 0.0,
      }
    });

    const result = await model.generateContent(query);
    const textResponse = result.response.text().trim();
    const symbol = normalizeTicker(textResponse);

    if (textResponse === "NOT_FOUND" || !symbol || !(await hasLiveQuote(symbol))) {
      return json(
        { error: "No matching US ticker found." },
        rateLimit,
        { status: 404 },
      );
    }

    // Return the resolved ticker
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

async function hasLiveQuote(ticker: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/stocks/${ticker}/quote`, {
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) return false;

    const payload = await response.json() as {
      status?: unknown;
      data?: { price?: unknown; symbol?: unknown };
    };
    return (
      payload.status === "success" &&
      typeof payload.data?.price === "number" &&
      normalizeTicker(String(payload.data?.symbol ?? "")) === ticker
    );
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
  const response = NextResponse.json(body, init)
  for (const [key, value] of Object.entries(rateLimitHeaders(rateLimit))) {
    response.headers.set(key, value)
  }
  return response
}
