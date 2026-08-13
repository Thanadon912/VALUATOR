import "server-only";

export interface NewsArticle {
  id: number;
  headline: string;
  summary: string;
  source: string;
  datetime: number;
  url: string;
  image: string;
}

export interface NewsResponse {
  ticker: string;
  articles: NewsArticle[];
  status: string;
}

const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8200";

export async function getNews(ticker: string): Promise<NewsResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/stocks/${ticker}/news`, {
      // Bucket C — Transient Dynamics. News feeds refresh realistically
      // throughout the trading day; isolate from the 14-day Bucket A
      // structural cache. 1800s = 30 min, matching the backend cap.
      next: { revalidate: 1800 },
      signal: AbortSignal.timeout(60000),
    });

    if (!response.ok) {
      return {
        ticker,
        articles: [],
        status: `News API returned ${response.status}.`,
      };
    }

    return (await response.json()) as NewsResponse;
  } catch {
    return {
      ticker,
      articles: [],
      status: "News API is not reachable. Start the FastAPI service and retry.",
    };
  }
}
