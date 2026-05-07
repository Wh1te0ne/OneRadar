import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiFeedPreviewItem, ApiFeedStateResponse } from "../api/types";
import { useAppState } from "../state/appState";

const DAILY_REFRESH_INTERVAL_MS = 5 * 60 * 1000;
const DAILY_FRESH_HOURS = 48;
const MAX_ITEMS_PER_SECTION = 4;

type DailyEntry = ApiFeedPreviewItem & {
  sourceUrl: string;
  sourceTitle: string;
};

type DailySection = {
  id: string;
  title: string;
  marker: string;
  description: string;
  entries: DailyEntry[];
};

const SECTION_DEFINITIONS = [
  {
    id: "models",
    title: "大模型技术进展",
    marker: "AI",
    description: "模型、训练、推理与多模态能力的最新变化。",
    keywords: ["ai", "artificial intelligence", "llm", "model", "gpt", "deepseek", "claude", "gemini", "openai", "mistral", "llama", "大模型", "模型", "推理", "多模态", "智能体", "agent"],
  },
  {
    id: "products",
    title: "产品与公司动态",
    marker: "Biz",
    description: "发布、融资、商业化和平台策略相关消息。",
    keywords: ["launch", "release", "product", "startup", "funding", "revenue", "market", "company", "发布", "上线", "产品", "公司", "融资", "商业化", "市场"],
  },
  {
    id: "developer",
    title: "开发者与开源",
    marker: "Dev",
    description: "框架、工具链、开源项目和工程实践更新。",
    keywords: ["github", "open source", "developer", "api", "sdk", "framework", "python", "rust", "javascript", "开源", "开发者", "框架", "工具", "代码", "接口"],
  },
  {
    id: "industry",
    title: "行业与研究",
    marker: "R&D",
    description: "研究论文、监管、算力和行业趋势。",
    keywords: ["research", "paper", "regulation", "policy", "chip", "gpu", "nvidia", "研究", "论文", "监管", "政策", "芯片", "算力", "行业"],
  },
] as const;

function parseTime(value?: string | null) {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : 0;
}

function formatShortDate(value?: string | null) {
  const time = parseTime(value);
  if (!time) return "未知时间";
  return new Date(time).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatRefreshTime(value?: string | null) {
  const time = parseTime(value);
  if (!time) return "还没有刷新记录";
  return new Date(time).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function isFresh(value?: string | null) {
  const time = parseTime(value);
  if (!time) return false;
  return Date.now() - time <= DAILY_FRESH_HOURS * 60 * 60 * 1000;
}

function truncateText(value: string | null | undefined, maxLength: number) {
  const text = (value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

function entryText(entry: DailyEntry) {
  return [entry.title, entry.summary ?? "", entry.author ?? "", entry.tags.join(" ")].join(" ").toLowerCase();
}

function sectionForEntry(entry: DailyEntry) {
  const haystack = entryText(entry);
  return SECTION_DEFINITIONS.find((section) => section.keywords.some((keyword) => haystack.includes(keyword))) ?? null;
}

function feedArticlePreviewPath(item: DailyEntry) {
  const params = new URLSearchParams({
    url: item.link,
    title: item.title,
    source_title: item.sourceTitle,
  });
  if (item.author) params.set("author", item.author);
  if (item.published_at) params.set("published_at", item.published_at);
  if (item.summary) params.set("summary", item.summary.slice(0, 600));
  if (item.is_saved) params.set("is_saved", "1");
  if (item.saved_item_id) params.set("saved_item_id", item.saved_item_id);
  if (item.saved_uid) params.set("saved_uid", item.saved_uid);
  return "/feed/preview?" + params.toString();
}

function sourceFeedPath(sourceUrl: string) {
  const params = new URLSearchParams({ source: sourceUrl });
  return "/feed?" + params.toString();
}

function entriesFromState(state: ApiFeedStateResponse) {
  return Object.values(state.feeds)
    .flatMap((feed) =>
      feed.items.map((item) => ({
        ...item,
        sourceUrl: feed.source_url,
        sourceTitle: feed.site_title,
      }))
    )
    .filter((entry) => isFresh(entry.published_at))
    .sort((a, b) => parseTime(b.published_at) - parseTime(a.published_at));
}

export function DailyNewsPage() {
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [feedState, setFeedState] = useState<ApiFeedStateResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAutoRefreshAt, setLastAutoRefreshAt] = useState<string | null>(null);

  const keyword = searchParams.get("q")?.trim().toLowerCase() ?? "";

  async function loadState(options?: { refresh?: boolean; silent?: boolean }) {
    if (options?.refresh) {
      setRefreshing(true);
    } else if (!options?.silent) {
      setLoading(true);
    }
    setError(null);
    try {
      if (options?.refresh) {
        await client.refreshFeeds();
        setLastAutoRefreshAt(new Date().toISOString());
      }
      const next = await client.getFeedState();
      setFeedState(next);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "每日新闻刷新失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadState();
    const timer = window.setInterval(() => {
      void loadState({ refresh: true, silent: true });
    }, DAILY_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);

  const allFreshEntries = useMemo(() => entriesFromState(feedState ?? { sources: [], feeds: {}, read_entries: [] }), [feedState]);

  const freshEntries = useMemo(() => {
    if (!keyword) return allFreshEntries;
    return allFreshEntries.filter((entry) => entryText(entry).includes(keyword));
  }, [allFreshEntries, keyword]);

  const sections = useMemo<DailySection[]>(() => {
    const grouped = new Map<string, DailyEntry[]>();
    SECTION_DEFINITIONS.forEach((section) => grouped.set(section.id, []));
    const other: DailyEntry[] = [];

    freshEntries.forEach((entry) => {
      const section = sectionForEntry(entry);
      if (section) {
        grouped.get(section.id)?.push(entry);
      } else {
        other.push(entry);
      }
    });

    const baseSections = SECTION_DEFINITIONS.map((section) => ({
      id: section.id,
      title: section.title,
      marker: section.marker,
      description: section.description,
      entries: (grouped.get(section.id) ?? []).slice(0, MAX_ITEMS_PER_SECTION),
    })).filter((section) => section.entries.length > 0);

    if (other.length > 0) {
      baseSections.push({
        id: "brief",
        title: "今日速览",
        marker: "News",
        description: "暂未归类但仍在新鲜度窗口内的订阅更新。",
        entries: other.slice(0, MAX_ITEMS_PER_SECTION),
      });
    }
    return baseSections;
  }, [freshEntries]);

  const leadEntry = freshEntries[0] ?? null;
  const sourceCount = feedState?.sources.length ?? 0;
  const failedSources = feedState?.sources.filter((source) => source.last_refresh_status === "failed") ?? [];
  const latestRefresh = feedState?.sources
    .map((source) => source.last_refreshed_at ?? source.last_loaded_at)
    .sort((a, b) => parseTime(b) - parseTime(a))[0] ?? lastAutoRefreshAt;

  return (
    <div className="daily-news-page">
      <header className="daily-news-header">
        <div className="daily-news-date-pill">{new Date().toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })}</div>
        <div className="daily-news-title-block">
          <p className="page-eyebrow">Daily Brief</p>
          <h2 className="page-title">每日新闻</h2>
          <p className="page-lead">聚合订阅源中最近 {DAILY_FRESH_HOURS} 小时的更新，按主题做轻量整理。</p>
        </div>
        <div className="daily-news-actions">
          <div className="daily-news-refresh-meta">
            <span>{sourceCount} 个订阅源</span>
            <span>最近刷新 {formatRefreshTime(latestRefresh)}</span>
          </div>
          <button className="btn btn-primary btn-sm" type="button" onClick={() => void loadState({ refresh: true })} disabled={refreshing || loading}>
            <span className="icon icon-sm">{refreshing ? "sync" : "refresh"}</span>
            {refreshing ? "刷新中…" : "主动刷新"}
          </button>
        </div>
      </header>

      {error && <div className="feedback feedback-error daily-news-feedback">{error}</div>}
      {failedSources.length > 0 && (
        <div className="feedback feedback-error daily-news-feedback">
          {failedSources.length} 个订阅源刷新失败，日报继续使用可用缓存。
        </div>
      )}

      {loading ? (
        <div className="daily-news-empty">
          <span className="icon icon-lg">sync</span>
          <h3>正在读取订阅源</h3>
        </div>
      ) : sourceCount === 0 ? (
        <div className="daily-news-empty">
          <span className="icon icon-lg">rss_feed</span>
          <h3>还没有订阅源</h3>
          <p>先添加 RSS 订阅源后，每日新闻会自动从这些源里整理最近更新。</p>
          <Link className="btn btn-secondary btn-sm" to="/feed">
            <span className="icon icon-sm">add</span>
            去添加订阅源
          </Link>
        </div>
      ) : freshEntries.length === 0 ? (
        <div className="daily-news-empty">
          <span className="icon icon-lg">event_busy</span>
          <h3>最近没有可进入日报的更新</h3>
          <p>新鲜度过滤只保留最近 {DAILY_FRESH_HOURS} 小时内容，旧文章会留在订阅源页。</p>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => void loadState({ refresh: true })} disabled={refreshing}>
            <span className="icon icon-sm">refresh</span>
            重新刷新
          </button>
        </div>
      ) : (
        <main className="daily-news-content">
          {leadEntry && (
            <section className="daily-news-lead">
              <p className="daily-news-source-line">
                <span className="daily-news-source-dot" />
                {leadEntry.sourceTitle} · {formatShortDate(leadEntry.published_at)}
              </p>
              <button type="button" className="daily-news-lead-title" onClick={() => navigate(feedArticlePreviewPath(leadEntry))}>
                {leadEntry.title}
              </button>
              <p>{truncateText(leadEntry.summary, 150) || "该订阅项没有提供摘要，点击后可进入预览阅读。"}</p>
              <Link to={sourceFeedPath(leadEntry.sourceUrl)} className="daily-news-source-link">
                查看订阅源
                <span className="icon icon-sm">chevron_right</span>
              </Link>
            </section>
          )}

          {sections.map((section) => (
            <section className="daily-news-section" key={section.id}>
              <div className="daily-news-section-heading">
                <span>{section.marker}</span>
                <div>
                  <h3>{section.title}</h3>
                  <p>{section.description}</p>
                </div>
              </div>

              <div className="daily-news-entry-list">
                {section.entries.map((entry) => (
                  <article className="daily-news-entry" key={`${entry.sourceUrl}:${entry.id || entry.link}`}>
                    <button type="button" className="daily-news-entry-title" onClick={() => navigate(feedArticlePreviewPath(entry))}>
                      {entry.title}
                    </button>
                    <p>{truncateText(entry.summary, 132) || "该订阅项没有提供摘要。"}</p>
                    <div className="daily-news-entry-footer">
                      <span>{entry.sourceTitle} · {formatShortDate(entry.published_at)}</span>
                      <Link to={sourceFeedPath(entry.sourceUrl)}>
                        查看订阅源
                        <span className="icon icon-sm">chevron_right</span>
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </main>
      )}
    </div>
  );
}
