import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiFeedPreviewItem, ApiFeedPreviewResponse } from "../api/types";
import { useAppState } from "../state/appState";

type FeedFilter = "all" | "fresh" | "tagged";

type SavedFeedSource = {
  sourceUrl: string;
  siteTitle: string;
  description?: string | null;
  lastLoadedAt: string;
};

const DEFAULT_RSS_URL = "https://blog.python.org/rss.xml";
const FEED_SOURCE_HISTORY_KEY = "oneradar.feed.sources.v1";
const MAX_SAVED_SOURCES = 5;

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

function loadSavedSources(): SavedFeedSource[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(FEED_SOURCE_HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((entry) => {
        if (!entry || typeof entry !== "object") {
          return null;
        }
        const candidate = entry as Partial<SavedFeedSource>;
        if (typeof candidate.sourceUrl !== "string" || typeof candidate.siteTitle !== "string") {
          return null;
        }
        return {
          sourceUrl: candidate.sourceUrl,
          siteTitle: candidate.siteTitle,
          description: typeof candidate.description === "string" ? candidate.description : null,
          lastLoadedAt: typeof candidate.lastLoadedAt === "string" ? candidate.lastLoadedAt : new Date().toISOString(),
        } satisfies SavedFeedSource;
      })
      .filter((entry): entry is SavedFeedSource => Boolean(entry));
  } catch {
    return [];
  }
}

function upsertSavedSource(list: SavedFeedSource[], next: SavedFeedSource): SavedFeedSource[] {
  return [next, ...list.filter((item) => item.sourceUrl !== next.sourceUrl)].slice(0, MAX_SAVED_SOURCES);
}

function describeSavedSource(source: SavedFeedSource) {
  try {
    return new URL(source.sourceUrl).host;
  } catch {
    return source.sourceUrl;
  }
}

export function FeedPage() {
  const [searchParams] = useSearchParams();
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);

  const [filter, setFilter] = useState<FeedFilter>("all");
  const [showAddRss, setShowAddRss] = useState(false);
  const [savedSources, setSavedSources] = useState<SavedFeedSource[]>(() => loadSavedSources());
  const [rssUrl, setRssUrl] = useState(() => loadSavedSources()[0]?.sourceUrl ?? DEFAULT_RSS_URL);
  const [feed, setFeed] = useState<ApiFeedPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);

  const keyword = searchParams.get("q")?.trim().toLowerCase() ?? "";

  useEffect(() => {
    try {
      window.localStorage.setItem(FEED_SOURCE_HISTORY_KEY, JSON.stringify(savedSources));
    } catch {
      // ignore persistence errors in preview mode
    }
  }, [savedSources]);

  async function loadFeed(targetUrl: string) {
    const url = targetUrl.trim();
    if (!url) {
      setError("请先输入 RSS 地址。");
      return;
    }
    setLoading(true);
    setError(null);
    setImportMessage(null);
    try {
      const next = await client.getFeedPreview(url, 20);
      setFeed(next);
      setRssUrl(next.source_url);
      setSavedSources((current) =>
        upsertSavedSource(current, {
          sourceUrl: next.source_url,
          siteTitle: next.site_title,
          description: next.description,
          lastLoadedAt: next.fetched_at,
        })
      );
    } catch (nextError) {
      setFeed(null);
      setError(nextError instanceof Error ? nextError.message : "RSS 读取失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadFeed(rssUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const items = feed?.items ?? [];
    return items.filter((item) => {
      if (filter === "fresh" && !isRecent(item.published_at)) return false;
      if (filter === "tagged" && !item.tags.length) return false;
      if (!keyword) return true;
      const haystack = [item.title, item.summary ?? "", item.author ?? "", item.tags.join(" ")].join(" ").toLowerCase();
      return haystack.includes(keyword);
    });
  }, [feed, filter, keyword]);

  async function handleImport(item: ApiFeedPreviewItem) {
    setImportingId(item.id);
    setImportMessage(null);
    try {
      const result = await client.importItem(item.link, "article");
      setImportMessage(result.is_duplicate ? `已存在：${result.uid}` : `已加入稍后阅读：${result.uid}`);
    } catch (nextError) {
      setImportMessage(nextError instanceof Error ? nextError.message : "导入失败");
    } finally {
      setImportingId(null);
    }
  }

  const freshCount = (feed?.items ?? []).filter((item) => isRecent(item.published_at)).length;
  const taggedCount = (feed?.items ?? []).filter((item) => item.tags.length > 0).length;

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
        <div style={{ display: "flex", alignItems: "center", gap: 2, background: "var(--surface-container)", padding: 4, borderRadius: "var(--radius-sm)" }}>
          {([
            ["all", "全部", (feed?.items ?? []).length],
            ["fresh", "近 7 天", freshCount],
            ["tagged", "有标签", taggedCount],
          ] as [FeedFilter, string, number][]).map(([value, label, count]) => (
            <button
              key={value}
              type="button"
              onClick={() => setFilter(value)}
              style={{
                padding: "5px 14px",
                borderRadius: "calc(var(--radius-sm) - 2px)",
                border: "none",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: filter === value ? 600 : 500,
                background: filter === value ? "var(--surface-lowest)" : "transparent",
                color: filter === value ? "var(--primary)" : "var(--on-surface-v)",
                boxShadow: filter === value ? "var(--shadow-card)" : "none",
                transition: "all 140ms ease",
              }}
            >
              {label} · {count}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {feed && (
            <div style={{ display: "flex", flexDirection: "column", minWidth: 0, alignItems: "flex-end" }}>
              <span style={{ fontSize: 12, color: "var(--on-surface)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {feed.site_title}
              </span>
              <span style={{ fontSize: 12, color: "var(--outline)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {feed.description ?? feed.site_url ?? feed.source_url} · {formatPublishedAt(feed.fetched_at)}
              </span>
            </div>
          )}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddRss((value) => !value)}>
            <span className="icon icon-sm">rss_feed</span>
            切换订阅源
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
            <button className="btn btn-primary btn-sm" type="button" disabled={loading} onClick={() => void loadFeed(rssUrl)}>
              <span className="icon icon-sm">sync</span>
              {loading ? "读取中…" : "加载预览"}
            </button>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => setRssUrl(DEFAULT_RSS_URL)}>
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
                  最近使用
                </span>
                <span style={{ fontSize: 12, color: "var(--outline)" }}>{savedSources.length} 个源</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {savedSources.map((source) => (
                  <button
                    key={source.sourceUrl}
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => void loadFeed(source.sourceUrl)}
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

      {importMessage && <div className="feedback feedback-success" style={{ margin: "12px 28px 0" }}>{importMessage}</div>}
      {error && <div className="feedback feedback-error" style={{ margin: "12px 28px 0" }}>{error}</div>}

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {loading && !feed ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <span className="icon icon-lg" style={{ color: "var(--outline)" }}>sync</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state" style={{ marginTop: 80 }}>
            <div className="empty-state-icon"><span className="icon icon-lg">rss_feed</span></div>
            <h3>{feed ? "当前筛选没有内容" : "还没有订阅内容"}</h3>
            <p>{feed ? "换一个筛选条件或 RSS 源试试。" : "点击右上角「切换订阅源」来加载公开 RSS，或从最近使用的源里直接选一个。"}</p>
          </div>
        ) : (
          filtered.map((item) => (
            <FeedRow key={item.id} item={item} isImporting={importingId === item.id} onImport={() => void handleImport(item)} />
          ))
        )}
      </div>
    </div>
  );
}

function FeedRow({ item, isImporting, onImport }: { item: ApiFeedPreviewItem; isImporting: boolean; onImport: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 0,
        padding: "0 28px",
        borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
        transition: "background 120ms ease",
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--surface-container)"; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = ""; }}
    >
      <div style={{ width: 8, height: 8, borderRadius: "50%", marginTop: 20, marginRight: 14, flexShrink: 0, background: "var(--primary)" }} />

      <div style={{ flex: 1, minWidth: 0, padding: "14px 0" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--on-surface-v)" }}>RSS</span>
          <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
          <span style={{ fontSize: 12, color: "var(--on-surface-v)" }}>{item.author ?? "未知作者"}</span>
          <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
          <span style={{ fontSize: 12, color: "var(--outline)" }}>{formatPublishedAt(item.published_at)}</span>
        </div>

        <a href={item.link} target="_blank" rel="noreferrer" style={{ display: "inline-block", textDecoration: "none" }}>
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
        </a>

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
        <a href={item.link} target="_blank" rel="noreferrer" className="topbar-icon-btn" title="打开原文" style={{ width: 28, height: 28 }}>
          <span className="icon icon-sm">open_in_new</span>
        </a>
        <button type="button" title="加入稍后阅读" className="topbar-icon-btn" onClick={onImport} disabled={isImporting} style={{ width: 28, height: 28 }}>
          <span className="icon icon-sm">bookmark_add</span>
        </button>
      </div>
    </div>
  );
}
