import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiFeedPreviewItem, ApiFeedPreviewResponse } from "../api/types";
import { useAppState } from "../state/appState";

type FeedFilter = "today" | "week" | "all";
type SelectedSource = "all" | string;

type SavedFeedSource = {
  sourceUrl: string;
  siteTitle: string;
  siteUrl?: string | null;
  description?: string | null;
  lastLoadedAt: string;
  lastRefreshStatus?: string | null;
  lastRefreshError?: string | null;
  lastRefreshedAt?: string | null;
  entryCount: number;
  todayCount: number;
  weekCount: number;
};

const DEFAULT_RSS_URL = "https://blog.python.org/rss.xml";

type FeedEntry = ApiFeedPreviewItem & {
  sourceUrl: string;
  sourceTitle: string;
  sourceDescription?: string | null;
};

type FeedPageSnapshot = {
  apiBaseUrl: string;
  savedSources: SavedFeedSource[];
  feeds: Record<string, ApiFeedPreviewResponse>;
  loadedWindow: FeedFilter | "all";
};

const FEED_PAGE_SNAPSHOT_KEY = "oneradar.feed.page.snapshot.v1";

let feedPageSnapshot: FeedPageSnapshot | null = null;

function parseStoredFeedPageSnapshot(apiBaseUrl: string): FeedPageSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(FEED_PAGE_SNAPSHOT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<FeedPageSnapshot>;
    if (
      parsed.apiBaseUrl !== apiBaseUrl ||
      !Array.isArray(parsed.savedSources) ||
      !parsed.feeds ||
      typeof parsed.feeds !== "object"
    ) {
      return null;
    }
    return {
      apiBaseUrl: parsed.apiBaseUrl,
      savedSources: parsed.savedSources,
      feeds: parsed.feeds as Record<string, ApiFeedPreviewResponse>,
      loadedWindow: (parsed.loadedWindow as FeedFilter | "all" | undefined) ?? "week",
    };
  } catch {
    return null;
  }
}

function rememberFeedPageSnapshot(snapshot: FeedPageSnapshot) {
  feedPageSnapshot = snapshot;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(FEED_PAGE_SNAPSHOT_KEY, JSON.stringify(snapshot));
  } catch {
    // A transient UI snapshot is optional; API state remains the source of truth.
  }
}

function formatPublishedAt(value?: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function isRecent(value?: string | null, days = 7) {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return Date.now() - date.getTime() <= days * 24 * 60 * 60 * 1000;
}

function isToday(value?: string | null) {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const today = new Date();
  return date.getFullYear() === today.getFullYear() && date.getMonth() === today.getMonth() && date.getDate() === today.getDate();
}

function upsertSavedSource(list: SavedFeedSource[], next: SavedFeedSource): SavedFeedSource[] {
  return [next, ...list.filter((item) => item.sourceUrl !== next.sourceUrl)];
}

function describeSavedSource(source: SavedFeedSource) {
  try {
    return new URL(source.sourceUrl).host;
  } catch {
    return source.sourceUrl;
  }
}

function compareByPublishedAt(a: FeedEntry, b: FeedEntry) {
  const left = a.published_at ? new Date(a.published_at).getTime() : 0;
  const right = b.published_at ? new Date(b.published_at).getTime() : 0;
  return right - left;
}

function sourceCount(source: SavedFeedSource, filter: FeedFilter) {
  if (filter === "today") return source.todayCount;
  if (filter === "week") return source.weekCount;
  return source.entryCount;
}

export function FeedPage() {
  const [searchParams] = useSearchParams();
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const cachedSnapshot = feedPageSnapshot?.apiBaseUrl === apiBaseUrl ? feedPageSnapshot : parseStoredFeedPageSnapshot(apiBaseUrl);

  const [filter, setFilter] = useState<FeedFilter>("week");
  const [selectedSource, setSelectedSource] = useState<SelectedSource>("all");
  const [showAddRss, setShowAddRss] = useState(false);
  const [savedSources, setSavedSources] = useState<SavedFeedSource[]>(cachedSnapshot?.savedSources ?? []);
  const [rssUrl, setRssUrl] = useState("");
  const [feeds, setFeeds] = useState<Record<string, ApiFeedPreviewResponse>>(cachedSnapshot?.feeds ?? {});
  const [loadedWindow, setLoadedWindow] = useState<FeedFilter | "all">(cachedSnapshot?.loadedWindow ?? "week");
  const [serverHydrated, setServerHydrated] = useState(false);
  const [loading, setLoading] = useState(!cachedSnapshot);
  const [error, setError] = useState<string | null>(null);

  const keyword = searchParams.get("q")?.trim().toLowerCase() ?? "";
  const sourceParam = searchParams.get("source")?.trim() ?? "";

  useEffect(() => {
    let cancelled = false;
    client.getFeedState("week")
      .then((state) => {
        if (cancelled) return;
        const serverSources = state.sources.map((source) => ({
          sourceUrl: source.source_url,
          siteTitle: source.site_title,
          siteUrl: source.site_url,
          description: source.description,
          lastLoadedAt: source.last_loaded_at,
          lastRefreshStatus: source.last_refresh_status,
          lastRefreshError: source.last_refresh_error,
          lastRefreshedAt: source.last_refreshed_at,
          entryCount: source.entry_count,
          todayCount: source.today_count,
          weekCount: source.week_count,
        }));
        const nextFeeds = state.feeds;
        if (!(cachedSnapshot && serverSources.length > 0 && Object.keys(nextFeeds).length === 0 && Object.keys(cachedSnapshot.feeds).length > 0)) {
          setFeeds(nextFeeds);
        }
        setSavedSources(serverSources);
        setLoadedWindow("week");
      })
      .catch((nextError) => {
        setError(nextError instanceof Error ? nextError.message : "订阅源状态读取失败");
      })
      .finally(() => {
        if (!cancelled) {
          setServerHydrated(true);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => {
    if (!serverHydrated && savedSources.length === 0 && Object.keys(feeds).length === 0) return;
    rememberFeedPageSnapshot({
      apiBaseUrl,
      savedSources,
      feeds,
      loadedWindow,
    });
  }, [apiBaseUrl, feeds, savedSources, loadedWindow, serverHydrated]);

  async function fetchFeed(targetUrl: string) {
    const url = targetUrl.trim();
    if (!url) {
      throw new Error("请先输入 RSS 地址。");
    }
    return client.getFeedPreview(url, 0);
  }

  function rememberFeed(next: ApiFeedPreviewResponse) {
    setFeeds((current) => ({ ...current, [next.source_url]: next }));
    setSavedSources((current) =>
      upsertSavedSource(current, {
        sourceUrl: next.source_url,
        siteTitle: next.site_title,
        siteUrl: next.site_url,
        description: next.description,
        lastLoadedAt: next.fetched_at,
        lastRefreshStatus: "success",
        lastRefreshError: null,
        lastRefreshedAt: new Date().toISOString(),
        entryCount: next.items.length,
        todayCount: next.items.filter((item) => isToday(item.published_at)).length,
        weekCount: next.items.filter((item) => isRecent(item.published_at)).length,
      })
    );
    void client.cacheFeedPreview(next).catch(() => {
      // Local cache remains available when server-side state persistence fails.
    });
  }

  async function loadFeed(targetUrl: string, options?: { select?: boolean }) {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchFeed(targetUrl);
      rememberFeed(next);
      setRssUrl("");
      if (options?.select) {
        setSelectedSource(next.source_url);
      }
      setShowAddRss(false);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : "RSS 读取失败";
      setError(message);
      const failedUrl = targetUrl.trim();
      if (failedUrl) {
        setSavedSources((current) =>
          upsertSavedSource(current, {
            sourceUrl: failedUrl,
            siteTitle: failedUrl,
            description: null,
            lastLoadedAt: new Date().toISOString(),
            lastRefreshStatus: "failed",
            lastRefreshError: message,
            lastRefreshedAt: new Date().toISOString(),
            entryCount: 0,
            todayCount: 0,
            weekCount: 0,
          })
        );
        void client.markFeedSourceError(failedUrl, message).catch(() => {
          // Local source error is already visible.
        });
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadState(window: FeedFilter | "all", options?: { silent?: boolean }) {
    if (!options?.silent) setLoading(true);
    setError(null);
    try {
      const state = await client.getFeedState(window);
      const serverSources = state.sources.map((source) => ({
        sourceUrl: source.source_url,
        siteTitle: source.site_title,
        siteUrl: source.site_url,
        description: source.description,
        lastLoadedAt: source.last_loaded_at,
        lastRefreshStatus: source.last_refresh_status,
        lastRefreshError: source.last_refresh_error,
        lastRefreshedAt: source.last_refreshed_at,
        entryCount: source.entry_count,
        todayCount: source.today_count,
        weekCount: source.week_count,
      }));
      setSavedSources(serverSources);
      setFeeds(state.feeds);
      setLoadedWindow(window);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "订阅源状态读取失败");
    } finally {
      if (!options?.silent) setLoading(false);
    }
  }

  async function refreshSources() {
    if (savedSources.length === 0) {
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await client.refreshFeeds();
      await loadState(filter, { silent: true });
      if (result.failed > 0) {
        const firstReason = Object.values(result.errors)[0] ?? "RSS 读取失败";
        setError(`${result.failed} 个订阅源刷新失败，已显示其余可用内容。原因：${firstReason}`);
      }
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "订阅源刷新失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!sourceParam) return;
    const knownSource = savedSources.some((source) => source.sourceUrl === sourceParam) || Boolean(feeds[sourceParam]);
    if (!knownSource) return;
    setSelectedSource(sourceParam);
    if (!feeds[sourceParam]) {
      void loadFeed(sourceParam);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceParam, serverHydrated, savedSources, feeds]);

  useEffect(() => {
    if (!serverHydrated) return;
    if (filter === "all" && loadedWindow !== "all") {
      void loadState("all");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, loadedWindow, serverHydrated]);

  const allEntries = useMemo(() => {
    return Object.values(feeds)
      .flatMap((feed) =>
        feed.items.map((item) => ({
          ...item,
          sourceUrl: feed.source_url,
          sourceTitle: feed.site_title,
          sourceDescription: feed.description,
        }))
      )
      .sort(compareByPublishedAt);
  }, [feeds]);

  const sourceEntries = useMemo(() => {
    if (selectedSource === "all") return allEntries;
    return allEntries.filter((item) => item.sourceUrl === selectedSource);
  }, [allEntries, selectedSource]);

  const filtered = useMemo(() => {
    const timeFiltered = sourceEntries.filter((item) => {
      if (filter === "today" && !isToday(item.published_at)) return false;
      if (filter === "week" && !isRecent(item.published_at)) return false;
      if (!keyword) return true;
      const haystack = [item.title, item.summary ?? "", item.author ?? "", item.sourceTitle, item.tags.join(" ")].join(" ").toLowerCase();
      return haystack.includes(keyword);
    });
    return timeFiltered;
  }, [sourceEntries, filter, keyword]);

  function removeSource(sourceUrl: string) {
    setSavedSources((current) => current.filter((source) => source.sourceUrl !== sourceUrl));
    setFeeds((current) => {
      const next = { ...current };
      delete next[sourceUrl];
      return next;
    });
    if (selectedSource === sourceUrl) {
      setSelectedSource("all");
    }
    void client.deleteFeedSource(sourceUrl).catch(() => {
      // Local removal has already happened; server sync can be retried on next mutation.
    });
  }

  function openOriginal(item: FeedEntry) {
    window.open(item.link, "_blank", "noopener,noreferrer");
  }

  const selectedSourceMeta = selectedSource === "all" ? null : savedSources.find((source) => source.sourceUrl === selectedSource) ?? null;
  const selectedCounts = selectedSourceMeta
    ? {
        today: selectedSourceMeta.todayCount,
        week: selectedSourceMeta.weekCount,
        all: selectedSourceMeta.entryCount,
      }
    : {
        today: savedSources.reduce((sum, source) => sum + source.todayCount, 0),
        week: savedSources.reduce((sum, source) => sum + source.weekCount, 0),
        all: savedSources.reduce((sum, source) => sum + source.entryCount, 0),
      };
  const selectedFeed = selectedSource === "all" ? null : feeds[selectedSource];
  const selectedSourceLabel = selectedFeed?.site_title ?? savedSources.find((source) => source.sourceUrl === selectedSource)?.siteTitle ?? "全部订阅源";
  const hasFeedSnapshot = serverHydrated || savedSources.length > 0 || Object.keys(feeds).length > 0;
  const awaitingInitialFeed = !hasFeedSnapshot;
  const countLabel = (count: number) => (awaitingInitialFeed ? "…" : String(count));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 28px",
          borderBottom: "1px solid rgba(var(--outline-rgb),0.18)",
          background: "var(--surface-lowest)",
          flexShrink: 0,
          gap: 16,
        }}
      >
        <div className="source-toolbar-left">
          <div className="source-page-title">
            <span>RSS</span>
            <h2>信息源</h2>
          </div>
          <div className="podcast-tabbar">
            {([
              ["today", "今天", countLabel(selectedCounts.today)],
              ["week", "近 7 天", countLabel(selectedCounts.week)],
              ["all", "全部", countLabel(selectedCounts.all)],
            ] as [FeedFilter, string, string][]).map(([value, label, count]) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label} · {count}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {selectedCounts[filter] > 0 && (
            <div style={{ display: "flex", flexDirection: "column", minWidth: 0, alignItems: "flex-end" }}>
              <span style={{ fontSize: 12, color: "var(--on-surface)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {selectedSourceLabel}
              </span>
              <span style={{ fontSize: 12, color: "var(--outline)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {savedSources.length || Object.keys(feeds).length ? `${Object.keys(feeds).length} 个已加载源 · ${selectedCounts[filter]} 条` : "订阅源发现流"}
              </span>
            </div>
          )}
          <button type="button" className="btn btn-primary btn-sm" onClick={() => void refreshSources()} disabled={loading}>
            <span className="icon icon-sm">sync</span>
            {loading ? "刷新中…" : "刷新订阅源"}
          </button>
        </div>
      </div>

      {showAddRss && (
        <div
          style={{
            padding: "12px 28px",
            background: "rgba(var(--primary-rgb),0.04)",
            borderBottom: "1px solid rgba(var(--primary-rgb),0.12)",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="icon icon-sm" style={{ color: "var(--primary)" }}>rss_feed</span>
            <input
              className="input"
              style={{ flex: 1, minWidth: 260, maxWidth: 520 }}
              value={rssUrl}
              onChange={(e) => setRssUrl(e.target.value)}
              placeholder="粘贴 RSS 源地址，例如 https://blog.python.org/rss.xml"
              autoFocus
            />
            <button className="btn btn-primary btn-sm" type="button" disabled={loading} onClick={() => void loadFeed(rssUrl, { select: true })}>
              <span className="icon icon-sm">sync</span>
              {loading ? "读取中…" : "添加并查看"}
            </button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => void loadFeed(DEFAULT_RSS_URL, { select: true })}>
              <span className="icon icon-sm">public</span>
              官方示例
            </button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setShowAddRss(false)}>
              <span className="icon icon-sm">close</span>
            </button>
          </div>

          {savedSources.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--outline-v)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  已订阅
                </span>
                <span style={{ fontSize: 12, color: "var(--outline)" }}>{savedSources.length} 个源</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {savedSources.map((source) => (
                  <button
                    key={source.sourceUrl}
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setSelectedSource(source.sourceUrl);
                      if (!feeds[source.sourceUrl]) void loadFeed(source.sourceUrl);
                    }}
                    disabled={loading && rssUrl === source.sourceUrl}
                    style={{ alignItems: "flex-start", textAlign: "left" }}
                  >
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{source.siteTitle}</span>
                      <span style={{ fontSize: 11, color: "var(--outline)" }}>
                        {describeSavedSource(source)} · {formatPublishedAt(source.lastLoadedAt)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {error && <div className="feedback feedback-error" style={{ margin: "12px 28px 0" }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", minHeight: 0, flex: 1 }}>
        <aside className="source-sidebar">
          <button
            type="button"
            className={`source-item source-item-button ${selectedSource === "all" ? "active" : ""}`}
            onClick={() => setSelectedSource("all")}
          >
            <span className="source-item-icon icon icon-sm">dynamic_feed</span>
            <span className="source-item-title">全部订阅源</span>
            <span className="source-item-count">{countLabel(selectedCounts[filter])}</span>
          </button>
          {savedSources.map((source) => {
            const loadedFeed = feeds[source.sourceUrl];
            const count = sourceCount(source, filter);
            return (
              <div
                key={source.sourceUrl}
                className={`source-item ${selectedSource === source.sourceUrl ? "active" : ""} ${source.lastRefreshStatus === "failed" ? "source-item-failed" : ""}`}
              >
                <button
                  type="button"
                  className="source-item-main"
                  title={source.lastRefreshStatus === "failed" && source.lastRefreshError ? source.lastRefreshError : undefined}
                  onClick={() => {
                    setSelectedSource(source.sourceUrl);
                    if (!loadedFeed) void loadFeed(source.sourceUrl);
                  }}
                >
                  <span className="source-item-icon icon icon-sm">rss_feed</span>
                  <span className="source-item-title">{loadedFeed?.site_title ?? source.siteTitle}</span>
                  <span className="source-item-count">{source.lastRefreshStatus === "failed" ? "!" : count}</span>
                </button>
                <button className="source-item-remove" type="button" title="移除订阅源" onClick={() => removeSource(source.sourceUrl)}>
                  <span className="icon icon-sm">close</span>
                </button>
              </div>
            );
          })}
          <button type="button" className="btn btn-ghost btn-sm" style={{ width: "100%", marginTop: 12, justifyContent: "center" }} onClick={() => setShowAddRss(true)}>
            <span className="icon icon-sm">add</span>
            添加订阅源
          </button>
        </aside>

        <main style={{ overflowY: "auto", padding: "8px 0" }}>
          {loading && allEntries.length === 0 ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
              <span className="icon icon-lg" style={{ color: "var(--outline)" }}>sync</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="empty-state" style={{ marginTop: 80 }}>
              <div className="empty-state-icon"><span className="icon icon-lg">rss_feed</span></div>
              <h3>{allEntries.length ? "当前筛选没有内容" : "还没有订阅内容"}</h3>
              <p>{allEntries.length ? "换一个时间范围、搜索词或订阅源试试。" : "添加 RSS 源后，这里会按发布时间聚合显示所有更新。"}</p>
            </div>
          ) : (
            filtered.map((item) => (
              <FeedRow
                key={`${item.sourceUrl}:${item.id}`}
                item={item}
                onOpen={() => openOriginal(item)}
              />
            ))
          )}
        </main>
      </div>
    </div>
  );
}

function FeedRow({
  item,
  onOpen,
}: {
  item: FeedEntry;
  onOpen: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 0,
        padding: "0 28px",
        borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
        transition: "background 120ms ease",
        cursor: "pointer",
      }}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--surface-container)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = ""; }}
    >
      <div style={{ flex: 1, minWidth: 0, padding: "14px 0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--on-surface-v)" }}>{item.sourceTitle}</span>
          <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
          <span style={{ fontSize: 12, color: "var(--on-surface-v)" }}>{item.author ?? "未知作者"}</span>
          <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
          <span style={{ fontSize: 12, color: "var(--outline)" }}>{formatPublishedAt(item.published_at)}</span>
        </div>

        <h3
          style={{
            fontFamily: "Manrope, sans-serif",
            fontSize: 15,
            fontWeight: 700,
            color: "var(--on-surface)",
            margin: "0 0 5px",
            lineHeight: 1.35,
          }}
        >
          {item.title}
        </h3>

        <p
          style={{
            fontSize: 13.5,
            color: "var(--on-surface-v)",
            margin: "0 0 8px",
            lineHeight: 1.6,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {item.summary ?? "该订阅项没有提供摘要。"}
        </p>

        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {item.tags.map((tag) => (
            <span key={tag} className="chip chip-neutral" style={{ fontSize: 11 }}>{tag}</span>
          ))}
          {isRecent(item.published_at) && <span className="chip chip-primary" style={{ fontSize: 11 }}>最近更新</span>}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8, padding: "14px 0 14px 16px", flexShrink: 0 }}>
        <a
          href={item.link}
          target="_blank"
          rel="noreferrer"
          className="topbar-icon-btn"
          title="打开原文"
          style={{ width: 28, height: 28 }}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <span className="icon icon-sm">open_in_new</span>
        </a>
      </div>
    </div>
  );
}
