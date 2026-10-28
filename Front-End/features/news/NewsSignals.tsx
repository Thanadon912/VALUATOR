"use client";

import {
  Bookmark,
  ChevronDown,
  ExternalLink,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveQuote } from "@/components/workspace/live-quote-provider";
import { TerminalHeader } from "@/features/valuation/components/terminal-header";
import styles from "./news-signals.module.css";

interface NewsArticle {
  id: number;
  headline: string;
  summary: string;
  source: string;
  timestamp: number;
  url: string;
  image: string;
  topic: string;
  relevance_score: number;
}

interface CompanyClassification {
  ticker: string;
  cik: string;
  sicCode: string;
  sicDescription: string;
  sector: string;
  industry: string;
  businessTags: string[];
  revenueSegments: string[];
  competitors: Array<{ ticker: string; overlapScore: number; reason: string }>;
  updatedAt: string;
  warnings?: string[];
}

interface NewsResponse {
  ticker: string;
  articles: NewsArticle[];
  status: string;
  classification?: CompanyClassification | null;
}

interface DcfResponse {
  underlying_assumptions?: {
    market_cap?: number | null;
    telemetry?: {
      market_cap?: number | null;
      beta?: number | null;
      risk_free_rate?: number | null;
      cost_of_equity?: number | null;
    };
  };
}

type DirectionalCue = "Positive cue" | "Negative cue" | "No directional cue";
type ProcessedArticle = NewsArticle & { directionalCue: DirectionalCue };

const POSITIVE_CUE_RE = /\b(beat|beats|gain|gains|growth|outperform|record|strong|surge|surges)\b/i;
const NEGATIVE_CUE_RE = /\b(decline|declines|drop|drops|investigation|lawsuit|miss|misses|weak|weaker)\b/i;
const PAGE_SIZE = 10;

function getRelativeTime(timestamp: number): string {
  const diff = Math.max(0, Math.floor(Date.now() / 1000) - timestamp);
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatEasternTimestamp(timestamp: number | null): string {
  if (!timestamp) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  }).format(new Date(timestamp * 1000));
}

function formatMarketCap(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function classifyDirectionalCue(article: NewsArticle): DirectionalCue {
  const text = `${article.headline} ${article.summary}`;
  if (POSITIVE_CUE_RE.test(text)) return "Positive cue";
  if (NEGATIVE_CUE_RE.test(text)) return "Negative cue";
  return "No directional cue";
}

function cueClassName(cue: DirectionalCue): string {
  if (cue === "Positive cue") return styles.cuePositive;
  if (cue === "Negative cue") return styles.cueNegative;
  return styles.cueNeutral;
}

async function requestWorkspaceData(ticker: string, signal: AbortSignal) {
  const [newsResult, dcfResult] = await Promise.allSettled([
    // Client requests must stay same-origin. Next.js rewrites this route to
    // the configured backend in every environment; embedding API_BASE_URL in
    // a client component previously baked the local 127.0.0.1 fallback into
    // the production browser bundle.
    fetch(`/api/stocks/${ticker}/news`, { signal }),
    fetch(`/api/v1/valuation/dcf?ticker=${ticker.toUpperCase()}`, { signal }),
  ]);

  let dcf: DcfResponse | null = null;
  if (dcfResult.status === "fulfilled" && dcfResult.value.ok) {
    try {
      dcf = (await dcfResult.value.json()) as DcfResponse;
    } catch {
      dcf = null;
    }
  }

  if (newsResult.status === "rejected") {
    return { news: null, dcf, newsError: getRequestErrorMessage(newsResult.reason) };
  }
  if (!newsResult.value.ok) {
    return {
      news: null,
      dcf,
      newsError: `News provider returned HTTP ${newsResult.value.status}.`,
    };
  }

  let news: NewsResponse;
  try {
    news = (await newsResult.value.json()) as NewsResponse;
  } catch {
    return { news: null, dcf, newsError: "The news provider returned an invalid response." };
  }
  if (!news.status.toLowerCase().startsWith("success")) {
    return {
      news: null,
      dcf,
      newsError: news.status || "News provider data is unavailable.",
    };
  }

  return { news, dcf, newsError: null };
}

function getRequestErrorMessage(requestError: unknown): string {
  if (requestError instanceof DOMException && requestError.name === "AbortError") {
    return "The news request timed out. Check the data service and try again.";
  }
  return requestError instanceof Error ? requestError.message : "The news feed could not be loaded.";
}

function SourceMark({ source }: { source: string }) {
  const label = source.trim() || "Unknown source";
  return (
    <span className={styles.sourceMark} aria-hidden="true">
      {label.slice(0, 2).toUpperCase()}
    </span>
  );
}

function NewsSkeleton() {
  return (
    <div className={styles.skeleton} aria-label="Loading news workspace" role="status">
      <span className="sr-only">Loading news workspace</span>
      <div className={styles.skeletonOverview} />
      <div className={styles.skeletonFeatured} />
      <div className={styles.skeletonToolbar} />
      <div className={styles.skeletonGrid}>
        <div className={styles.skeletonFeed} />
        <div className={styles.skeletonAside} />
      </div>
    </div>
  );
}

function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
}: {
  title: string;
  message: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className={styles.emptyState} role="status">
      <h2>{title}</h2>
      <p>{message}</p>
      <button type="button" className={styles.secondaryButton} onClick={onAction}>
        {actionLabel}
      </button>
    </div>
  );
}

function ArticleActions({
  story,
  bookmarked,
  onBookmark,
}: {
  story: ProcessedArticle;
  bookmarked: boolean;
  onBookmark: (story: ProcessedArticle) => void;
}) {
  return (
    <div className={styles.articleActions}>
      <button
        type="button"
        className={`${styles.iconButton} ${bookmarked ? styles.iconButtonActive : ""}`}
        onClick={() => onBookmark(story)}
        aria-label={`${bookmarked ? "Remove" : "Save"} ${story.headline}`}
        aria-pressed={bookmarked}
      >
        <Bookmark className={bookmarked ? styles.bookmarkFilled : ""} aria-hidden="true" />
      </button>
      <a
        className={styles.iconButton}
        href={story.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${story.headline} from ${story.source} in a new tab`}
      >
        <ExternalLink aria-hidden="true" />
      </a>
    </div>
  );
}

export function NewsSignals({ ticker }: { ticker: string }) {
  const [data, setData] = useState<NewsResponse | null>(null);
  const [dcfData, setDcfData] = useState<DcfResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTopic, setActiveTopic] = useState("All topics");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"Latest" | "Oldest">("Latest");
  const [timeRange, setTimeRange] = useState<"24h" | "7d" | "30d">("30d");
  const [showSavedOnly, setShowSavedOnly] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<number>>(new Set());
  const [bookmarkAnnouncement, setBookmarkAnnouncement] = useState("");
  const [currentTimestamp] = useState(() => Math.floor(Date.now() / 1000));
  const { data: liveQuote } = useLiveQuote();

  const storageKey = `valuator:news-bookmarks:${ticker.toUpperCase()}`;

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => {
      try {
        const saved = window.localStorage.getItem(storageKey);
        setBookmarkedIds(saved ? new Set(JSON.parse(saved) as number[]) : new Set());
      } catch {
        setBookmarkedIds(new Set());
      }
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [storageKey]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 30000);

    try {
      const result = await requestWorkspaceData(ticker, controller.signal);
      setData(result.news);
      setDcfData(result.dcf);
      setError(result.newsError);
    } catch (requestError) {
      setData(null);
      setError(getRequestErrorMessage(requestError));
    } finally {
      window.clearTimeout(timeoutId);
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 30000);

    requestWorkspaceData(ticker, controller.signal)
      .then((result) => {
        if (!active) return;
        setData(result.news);
        setDcfData(result.dcf);
        setError(result.newsError);
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        setData(null);
        setError(getRequestErrorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
        window.clearTimeout(timeoutId);
      });

    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [ticker]);

  const processedArticles = useMemo<ProcessedArticle[]>(
    () =>
      (data?.articles ?? []).map((article) => ({
        ...article,
        topic: article.topic?.trim() || "Company",
        source: article.source?.trim() || "Unknown source",
        directionalCue: classifyDirectionalCue(article),
      })),
    [data],
  );

  const topics = useMemo(
    () => ["All topics", ...Array.from(new Set(processedArticles.map((article) => article.topic))).sort()],
    [processedArticles],
  );

  const filteredArticles = useMemo(() => {
    const timeLimit = timeRange === "24h" ? 86400 : timeRange === "7d" ? 604800 : 2592000;
    const query = searchQuery.trim().toLocaleLowerCase();

    return processedArticles
      .filter((article) => !showSavedOnly || bookmarkedIds.has(article.id))
      .filter((article) => activeTopic === "All topics" || article.topic === activeTopic)
      .filter((article) => currentTimestamp - article.timestamp <= timeLimit)
      .filter(
        (article) =>
          !query ||
          article.headline.toLocaleLowerCase().includes(query) ||
          article.summary.toLocaleLowerCase().includes(query) ||
          article.source.toLocaleLowerCase().includes(query),
      )
      .sort((a, b) => (sortBy === "Latest" ? b.timestamp - a.timestamp : a.timestamp - b.timestamp));
  }, [activeTopic, bookmarkedIds, currentTimestamp, processedArticles, searchQuery, showSavedOnly, sortBy, timeRange]);

  const analytics = useMemo(() => {
    const directionalCounts: Record<DirectionalCue, number> = {
      "Positive cue": 0,
      "Negative cue": 0,
      "No directional cue": 0,
    };
    const topicCounts = new Map<string, number>();
    const sourceCounts = new Map<string, number>();

    for (const article of filteredArticles) {
      directionalCounts[article.directionalCue] += 1;
      topicCounts.set(article.topic, (topicCounts.get(article.topic) ?? 0) + 1);
      sourceCounts.set(article.source, (sourceCounts.get(article.source) ?? 0) + 1);
    }

    const total = filteredArticles.length;
    const percentage = (count: number) => (total ? Math.round((count / total) * 100) : 0);
    return {
      total,
      uniqueSources: sourceCounts.size,
      newestTimestamp: total ? Math.max(...filteredArticles.map((article) => article.timestamp)) : null,
      directional: [
        { label: "Positive cue" as const, value: percentage(directionalCounts["Positive cue"]) },
        { label: "No directional cue" as const, value: percentage(directionalCounts["No directional cue"]) },
        { label: "Negative cue" as const, value: percentage(directionalCounts["Negative cue"]) },
      ],
      topics: Array.from(topicCounts.entries())
        .map(([label, count]) => ({ label, value: percentage(count), count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 6),
      sources: Array.from(sourceCounts.entries())
        .map(([label, count]) => ({ label, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 5),
    };
  }, [filteredArticles]);

  const telemetry = dcfData?.underlying_assumptions?.telemetry;
  const marketCap = dcfData?.underlying_assumptions?.market_cap ?? telemetry?.market_cap ?? null;
  const featuredStory = showSavedOnly ? null : (filteredArticles[0] ?? null);
  const feed = filteredArticles.slice(featuredStory ? 1 : 0);
  const visibleFeed = feed.slice(0, visibleCount);
  const hasActiveFilters =
    activeTopic !== "All topics" ||
    searchQuery.trim().length > 0 ||
    timeRange !== "30d" ||
    sortBy !== "Latest" ||
    showSavedOnly;

  const resetFilters = () => {
    setActiveTopic("All topics");
    setSearchQuery("");
    setSortBy("Latest");
    setTimeRange("30d");
    setShowSavedOnly(false);
    setVisibleCount(PAGE_SIZE);
  };

  const toggleBookmark = (story: ProcessedArticle) => {
    setBookmarkedIds((previous) => {
      const next = new Set(previous);
      const removing = next.has(story.id);
      if (removing) next.delete(story.id);
      else next.add(story.id);
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(Array.from(next)));
      } catch {
        // The in-memory state remains usable when storage is unavailable.
      }
      setBookmarkAnnouncement(`${removing ? "Removed" : "Saved"}: ${story.headline}`);
      return next;
    });
  };

  return (
    <div className={styles.page}>
      <TerminalHeader
        tickerSymbol={ticker.toUpperCase()}
        currentPrice={liveQuote?.data?.price ?? null}
        marketCap={formatMarketCap(marketCap)}
        beta={telemetry?.beta ?? null}
        riskFreeRate={telemetry?.risk_free_rate != null ? telemetry.risk_free_rate * 100 : null}
        costOfEquity={telemetry?.cost_of_equity != null ? telemetry.cost_of_equity * 100 : null}
      />

      <main className={styles.workspace} id="main-content">
        <header className={styles.pageHeader}>
          <div>
            <h1>{ticker.toUpperCase()} news intelligence</h1>
            <p>Provider headlines with transparent, app-derived directional cues and topic coverage.</p>
          </div>
          <div className={styles.headerStatus} aria-label="News timing">
            <span className={styles.liveDot} aria-hidden="true" />
            <span>{analytics.newestTimestamp ? `Latest item ${formatEasternTimestamp(analytics.newestTimestamp)}` : "Awaiting provider data"}</span>
          </div>
        </header>

        {loading ? (
          <NewsSkeleton />
        ) : error ? (
          <EmptyState title="News feed unavailable" message={error} actionLabel="Retry news feed" onAction={() => void loadData()} />
        ) : processedArticles.length === 0 ? (
          <EmptyState
            title="No provider articles available"
            message={`The provider returned no current articles for ${ticker.toUpperCase()}. No fallback stories were generated.`}
            actionLabel="Check again"
            onAction={() => void loadData()}
          />
        ) : (
          <>
            <section className={styles.overview} aria-labelledby="overview-heading">
              <div className={styles.overviewHeading}>
                <h2 id="overview-heading">Coverage snapshot</h2>
                <span className={styles.factLabel}>Provider feed</span>
              </div>
              <dl className={styles.overviewMetrics}>
                <div>
                  <dt>Matching stories</dt>
                  <dd>{analytics.total}</dd>
                </div>
                <div>
                  <dt>Distinct sources</dt>
                  <dd>{analytics.uniqueSources}</dd>
                </div>
                <div>
                  <dt>Coverage window</dt>
                  <dd>{timeRange}</dd>
                </div>
                <div>
                  <dt>Saved locally</dt>
                  <dd>{bookmarkedIds.size}</dd>
                </div>
              </dl>
            </section>

            {featuredStory && (
              <section className={styles.featured} aria-labelledby="featured-heading">
                <div className={styles.featuredContent}>
                  <div className={styles.sectionHeadingRow}>
                    <h2 id="featured-heading">Lead story</h2>
                    <span className={styles.factLabel}>Provider content</span>
                  </div>
                  <a href={featuredStory.url} target="_blank" rel="noopener noreferrer" className={styles.featuredLink}>
                    <h3>{featuredStory.headline}</h3>
                  </a>
                  {featuredStory.summary && <p>{featuredStory.summary}</p>}
                  <div className={styles.featuredMeta}>
                    <span>{featuredStory.source}</span>
                    <span aria-hidden="true">•</span>
                    <time dateTime={new Date(featuredStory.timestamp * 1000).toISOString()}>
                      {getRelativeTime(featuredStory.timestamp)}
                    </time>
                    <span className={styles.topicChip}>{featuredStory.topic}</span>
                  </div>
                </div>
                <div className={styles.featuredSignal}>
                  <span className={styles.derivedLabel}>App-derived</span>
                  <strong className={cueClassName(featuredStory.directionalCue)}>{featuredStory.directionalCue}</strong>
                  <p>Keyword cue only. It is not investment sentiment or a confidence score.</p>
                  <ArticleActions
                    story={featuredStory}
                    bookmarked={bookmarkedIds.has(featuredStory.id)}
                    onBookmark={toggleBookmark}
                  />
                </div>
              </section>
            )}

            <section className={styles.controls} aria-label="News filters">
              <label className={styles.searchField}>
                <span className="sr-only">Search headlines, summaries, and sources</span>
                <Search aria-hidden="true" />
                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(event.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                  placeholder="Search headlines, summaries, or sources"
                />
              </label>
              <label className={styles.selectField}>
                <span>Topic</span>
                <select
                  value={activeTopic}
                  onChange={(event) => {
                    setActiveTopic(event.target.value);
                    setVisibleCount(PAGE_SIZE);
                  }}
                >
                  {topics.map((topic) => (
                    <option key={topic}>{topic}</option>
                  ))}
                </select>
                <ChevronDown aria-hidden="true" />
              </label>
              <label className={styles.selectField}>
                <span>Window</span>
                <select
                  value={timeRange}
                  onChange={(event) => {
                    setTimeRange(event.target.value as "24h" | "7d" | "30d");
                    setVisibleCount(PAGE_SIZE);
                  }}
                >
                  <option value="24h">Past 24 hours</option>
                  <option value="7d">Past 7 days</option>
                  <option value="30d">Past 30 days</option>
                </select>
                <ChevronDown aria-hidden="true" />
              </label>
              <label className={styles.selectField}>
                <span>Order</span>
                <select
                  value={sortBy}
                  onChange={(event) => {
                    setSortBy(event.target.value as "Latest" | "Oldest");
                    setVisibleCount(PAGE_SIZE);
                  }}
                >
                  <option value="Latest">Newest first</option>
                  <option value="Oldest">Oldest first</option>
                </select>
                <ChevronDown aria-hidden="true" />
              </label>
              <button
                type="button"
                className={`${styles.savedButton} ${showSavedOnly ? styles.savedButtonActive : ""}`}
                onClick={() => {
                  setShowSavedOnly((current) => !current);
                  setVisibleCount(PAGE_SIZE);
                }}
                aria-pressed={showSavedOnly}
              >
                <Bookmark className={showSavedOnly ? styles.bookmarkFilled : ""} aria-hidden="true" />
                Saved
                <span>{bookmarkedIds.size}</span>
              </button>
              {hasActiveFilters && (
                <button type="button" className={styles.resetButton} onClick={resetFilters}>
                  Reset
                </button>
              )}
            </section>

            <div className={styles.contentGrid}>
              <section className={styles.feed} aria-labelledby="feed-heading">
                <div className={styles.feedHeader}>
                  <div>
                    <h2 id="feed-heading">Latest coverage</h2>
                    <p aria-live="polite">{analytics.total} matching {analytics.total === 1 ? "story" : "stories"}</p>
                  </div>
                  <button type="button" className={styles.refreshButton} onClick={() => void loadData()}>
                    <RefreshCw aria-hidden="true" />
                    Refresh
                  </button>
                </div>

                {filteredArticles.length === 0 ? (
                  <EmptyState
                    title="No stories match these filters"
                    message="Broaden the time window, topic, or search query. Provider data has not been replaced with placeholders."
                    actionLabel="Reset filters"
                    onAction={resetFilters}
                  />
                ) : visibleFeed.length === 0 ? (
                  <p className={styles.singleStoryMessage}>The lead story is the only match for these filters.</p>
                ) : (
                  <div className={styles.feedList}>
                    {visibleFeed.map((story) => (
                      <article className={styles.articleRow} key={story.id}>
                        <div className={styles.articlePrimary}>
                          <a href={story.url} target="_blank" rel="noopener noreferrer">
                            <h3>{story.headline}</h3>
                          </a>
                          {story.summary && <p>{story.summary}</p>}
                        </div>
                        <div className={styles.articleSource}>
                          <SourceMark source={story.source} />
                          <span>{story.source}</span>
                        </div>
                        <div className={styles.articleTiming}>
                          <time dateTime={new Date(story.timestamp * 1000).toISOString()}>{getRelativeTime(story.timestamp)}</time>
                          <span>{story.topic}</span>
                        </div>
                        <div className={styles.articleSignal}>
                          <span className={`${styles.cueChip} ${cueClassName(story.directionalCue)}`}>
                            {story.directionalCue}
                          </span>
                        </div>
                        <ArticleActions story={story} bookmarked={bookmarkedIds.has(story.id)} onBookmark={toggleBookmark} />
                      </article>
                    ))}
                  </div>
                )}

                {feed.length > visibleCount && (
                  <button
                    type="button"
                    className={styles.loadMoreButton}
                    onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
                  >
                    Show {Math.min(PAGE_SIZE, feed.length - visibleCount)} more stories
                    <ChevronDown aria-hidden="true" />
                  </button>
                )}
              </section>

              <aside className={styles.analysisRail} aria-label="News analysis">
                <section className={styles.analysisSection} aria-labelledby="cue-heading">
                  <div className={styles.sectionHeadingRow}>
                    <h2 id="cue-heading">Directional cue mix</h2>
                    <span className={styles.derivedLabel}>App-derived</span>
                  </div>
                  <p className={styles.analysisIntro}>Keyword occurrence across the currently filtered headlines and summaries.</p>
                  <div className={styles.barList}>
                    {analytics.directional.map((item) => (
                      <div className={styles.barItem} key={item.label}>
                        <div>
                          <span>{item.label}</span>
                          <strong>{item.value}%</strong>
                        </div>
                        <div className={styles.barTrack}>
                          <span className={cueClassName(item.label)} style={{ inlineSize: `${item.value}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                <section className={styles.analysisSection} aria-labelledby="topic-heading">
                  <div className={styles.sectionHeadingRow}>
                    <h2 id="topic-heading">Topic distribution</h2>
                    <span className={styles.factLabel}>Provider labels</span>
                  </div>
                  {analytics.topics.length ? (
                    <div className={styles.topicList}>
                      {analytics.topics.map((topic) => (
                        <div key={topic.label}>
                          <span title={topic.label}>{topic.label}</span>
                          <strong>{topic.count}</strong>
                          <div className={styles.topicTrack}>
                            <span style={{ inlineSize: `${topic.value}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className={styles.unavailableText}>Topic labels are unavailable for the current result set.</p>
                  )}
                </section>

                <section className={styles.analysisSection} aria-labelledby="source-heading">
                  <div className={styles.sectionHeadingRow}>
                    <h2 id="source-heading">Source concentration</h2>
                    <span className={styles.factLabel}>Provider feed</span>
                  </div>
                  <ol className={styles.sourceList}>
                    {analytics.sources.map((source) => (
                      <li key={source.label}>
                        <span>{source.label}</span>
                        <strong>{source.count}</strong>
                      </li>
                    ))}
                  </ol>
                </section>

                <details className={styles.methodology}>
                  <summary>
                    <span>How derived cues work</span>
                    <ChevronDown aria-hidden="true" />
                  </summary>
                  <div>
                    <p>
                      Directional cues use bounded keyword matching on provider headlines and summaries. They are app-derived,
                      do not use the provider relevance score, and are not a recommendation or confidence measure.
                    </p>
                    <p>Verify material developments with the linked publisher or a primary filing.</p>
                    {data?.classification?.updatedAt && (
                      <p>Company topic classification updated {new Date(data.classification.updatedAt).toLocaleDateString("en-US")}.</p>
                    )}
                  </div>
                </details>
              </aside>
            </div>
          </>
        )}
        <p className="sr-only" aria-live="polite">{bookmarkAnnouncement}</p>
      </main>

      <footer className="mt-12 border-t border-[#1A2E20] bg-[#0A0D0B] px-4 py-8 md:px-6">
        <div className="mx-auto max-w-[1440px] flex flex-col gap-3 text-xs leading-relaxed text-[#869E8F]">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#B7FF3C]" aria-hidden="true" />
            <div className="space-y-1.5">
              <h3 className="font-semibold text-[#E0E6E2]">
                Market News &amp; Sentiment Analysis Disclaimer
              </h3>
              <p>
                News articles, directional cues, and topic classifications are aggregated from third-party publishers for informational and contextual research only. Sentiment and topic indicators are automated heuristics and do not constitute trading signals, investment advice, or publisher endorsements.
              </p>
            </div>
          </div>
          <div className="border-t border-[#1A2E20]/60 pt-3 text-[11px] text-[#869E8F]">
            VALUATOR · For informational research only — not investment advice.
          </div>
        </div>
      </footer>
    </div>
  );
}
