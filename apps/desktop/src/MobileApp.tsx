import { FormEvent, useEffect, useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createApiClient } from "./api";
import type {
  ApiBilibiliIntegrationSettings,
  ApiBilibiliQrcodeGenerateResponse,
  ApiDailyNewsEntry,
  ApiDailyNewsReportResponse,
  ApiFeedPreviewItem,
  ApiFeedPreviewResponse,
  ApiFeedSourceEntry,
  ApiItemSummary,
  ApiProvider,
} from "./api";
import { FeedArticlePreviewPage } from "./pages/FeedArticlePreviewPage";
import { ItemDetailPage } from "./pages/ItemDetailPage";
import { useAppState } from "./state/appState";
import { hasConfiguredLlmProvider } from "./utils/providers";

type MobileTab = "daily" | "inbox" | "feed" | "library" | "me";
type MobileToast = { message: string; tone: "success" | "error" | "info" } | null;

type FeedEntry = ApiFeedPreviewItem & {
  sourceUrl: string;
  sourceTitle: string;
};

const DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";
const DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1";

type ProviderKind = "doubao" | "openai_compatible" | "deepseek" | "custom";
type ProviderCapability = "llm" | "asr";
type ThinkingMode = "default" | "enabled" | "disabled";
type ModelInputCapability = "text" | "image" | "audio" | "video";

const modelInputCapabilityOptions: Array<{ value: ModelInputCapability; label: string }> = [
  { value: "text", label: "文字" },
  { value: "image", label: "图片" },
  { value: "audio", label: "音频" },
  { value: "video", label: "视频" },
];

type ProviderFormState = {
  id: string | null;
  capability: ProviderCapability;
  input_capabilities: ModelInputCapability[];
  provider_name: string;
  provider_type: ProviderKind;
  base_url: string;
  api_key: string;
  chat_model: string;
  transcription_model: string;
  transcription_app_id: string;
  transcription_access_token: string;
  transcription_secret_key: string;
  thinking_mode: ThinkingMode;
};

function todayDate() {
  return dateKey(new Date());
}

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

function shiftDate(value: string, days: number) {
  const date = parseDate(value);
  date.setDate(date.getDate() + days);
  return dateKey(date);
}

function displayDay(value: string) {
  return String(parseDate(value).getDate()).padStart(2, "0");
}

function displayWeekday(value: string) {
  return parseDate(value).toLocaleDateString("zh-CN", { weekday: "short" });
}

function displayTime(value?: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function normalizeQuickAddUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function isBilibiliUrl(value: string) {
  try {
    const host = new URL(value).hostname.toLowerCase();
    return host === "b23.tv" || host.endsWith(".b23.tv") || host === "bilibili.com" || host.endsWith(".bilibili.com");
  } catch {
    return false;
  }
}

function itemTypeLabel(type: ApiItemSummary["content_type"]) {
  if (type === "bilibili_video") return "视频";
  if (type === "podcast_episode") return "播客";
  return "文章";
}

function statusLabel(status: ApiItemSummary["status"]) {
  if (status === "completed") return "可阅读";
  if (status === "processing") return "处理中";
  if (status === "failed") return "失败";
  return "待处理";
}

function compactSource(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function feedArticlePreviewPath(item: FeedEntry | ApiDailyNewsEntry) {
  const params = new URLSearchParams({
    url: item.link,
    title: item.title,
    source_title: "sourceTitle" in item ? item.sourceTitle : item.source_title,
  });
  if (item.author) params.set("author", item.author);
  if (item.published_at) params.set("published_at", item.published_at);
  if (item.summary) params.set("summary", item.summary.slice(0, 600));
  return "/feed/preview?" + params.toString();
}

function dispatchToast(message: string, tone: NonNullable<MobileToast>["tone"] = "info") {
  window.dispatchEvent(new CustomEvent("oneradar:toast", { detail: { message, tone } }));
}

function MobileIcon({ name, filled = false }: { name: string; filled?: boolean }) {
  return <span className={`icon${filled ? " icon-fill" : ""}`}>{name}</span>;
}

function MobileTopBar({ onAdd }: { onAdd: () => void }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";

  function setQuery(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set("q", value);
    else next.delete("q");
    setSearchParams(next, { replace: true });
  }

  return (
    <header className="mobile-topbar">
      <label className="mobile-search" aria-label="搜索">
        <MobileIcon name="search" />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索稍后阅读" />
      </label>
      <button type="button" className="mobile-topbar-btn" aria-label="导入链接" onClick={onAdd}>
        <MobileIcon name="add" />
      </button>
    </header>
  );
}

function mobileTabFromPath(pathname: string): MobileTab {
  if (pathname === "/" || pathname.startsWith("/daily") || pathname.startsWith("/share/daily")) return "daily";
  if (pathname.startsWith("/inbox") || pathname.startsWith("/items") || pathname.startsWith("/reader")) return "inbox";
  if (pathname.startsWith("/feed")) return "feed";
  if (pathname.startsWith("/library") || pathname.startsWith("/folders")) return "library";
  if (pathname.startsWith("/me") || pathname.startsWith("/settings") || pathname.startsWith("/connect")) return "me";
  return "daily";
}

function MobileBottomNav() {
  const location = useLocation();
  const activeTab = mobileTabFromPath(location.pathname);
  const items = [
    { to: "/daily", label: "日报", icon: "newspaper", tab: "daily" as MobileTab },
    { to: "/inbox", label: "稍后", icon: "bookmark", tab: "inbox" as MobileTab },
    { to: "/feed", label: "订阅", icon: "rss_feed", tab: "feed" as MobileTab },
    { to: "/library", label: "知识库", icon: "local_library", tab: "library" as MobileTab },
    { to: "/me", label: "我", icon: "person", tab: "me" as MobileTab },
  ];
  return (
    <nav className="mobile-bottom-nav" aria-label="移动端导航">
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} className={`mobile-bottom-link ${activeTab === item.tab ? "active" : ""}`}>
          <MobileIcon name={item.icon} filled={activeTab === item.tab} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function MobileDateStrip({ selectedDate, onSelect }: { selectedDate: string; onSelect: (date: string) => void }) {
  const dates = Array.from({ length: 7 }, (_, index) => shiftDate(todayDate(), index - 6));
  return (
    <div className="mobile-date-strip" aria-label="日报日期">
      <div className="mobile-date-track">
        {dates.map((date) => {
          const selected = date === selectedDate;
          return (
            <button key={date} type="button" className={`mobile-date-tile ${selected ? "active" : ""}`} onClick={() => onSelect(date)}>
              <strong>{date === todayDate() ? "今" : displayDay(date)}</strong>
              <span>{displayWeekday(date)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function MobileDailyPage() {
  const { apiBaseUrl, loadProviders, providers } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedDate = searchParams.get("date") || todayDate();
  const keyword = (searchParams.get("q") ?? "").trim().toLowerCase();
  const [report, setReport] = useState<ApiDailyNewsReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setDate(date: string) {
    const next = new URLSearchParams(searchParams);
    if (date === todayDate()) next.delete("date");
    else next.set("date", date);
    setSearchParams(next);
  }

  async function loadReport(date: string) {
    setLoading(true);
    setError(null);
    try {
      setReport(await client.getDailyNews(date));
    } catch (nextError) {
      setReport(null);
      setError(nextError instanceof Error ? nextError.message : "日报读取失败");
    } finally {
      setLoading(false);
    }
  }

  async function generate(force: boolean) {
    setGenerating(true);
    setError(null);
    try {
      const loadedProviders = hasConfiguredLlmProvider(providers) ? providers : await loadProviders();
      if (!hasConfiguredLlmProvider(loadedProviders)) {
        setError("还没有配置可用的大语言模型，请先到「我」里的设置配置模型服务。");
        return;
      }
      setReport(await client.generateDailyNews(selectedDate, force));
      dispatchToast(force ? "已重新生成日报" : "已生成日报", "success");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => {
    void loadReport(selectedDate);
  }, [selectedDate, client]);

  const sections = useMemo(() => {
    const source = report?.sections ?? [];
    if (!keyword) return source;
    return source
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => `${item.title} ${item.summary} ${section.title}`.toLowerCase().includes(keyword)),
      }))
      .filter((section) => `${section.title} ${section.summary}`.toLowerCase().includes(keyword) || section.items.length > 0);
  }, [keyword, report]);

  return (
    <section className="mobile-screen mobile-daily-screen">
      <div className="mobile-section-title">
        <p>Daily Brief</p>
        <h1>每日新闻</h1>
      </div>
      <MobileDateStrip selectedDate={selectedDate} onSelect={setDate} />

      {loading && <div className="mobile-empty">正在读取日报…</div>}
      {error && <div className="mobile-alert">{error}</div>}

      {!loading && report?.status !== "ready" && (
        <div className="mobile-generate-panel">
          <div className="mobile-generate-icon"><MobileIcon name="draft" /></div>
          <div>
            <h2>这一天还没有日报</h2>
            <p>会基于同一套订阅源缓存和账号数据生成，不会产生移动端独立数据。</p>
          </div>
          <button type="button" className="mobile-primary-btn" disabled={generating} onClick={() => void generate(false)}>
            {generating ? "生成中…" : "生成这一天"}
          </button>
        </div>
      )}

      {!loading && report?.status === "ready" && (
        <article className="mobile-daily-article">
          {report.lead && (
            <button type="button" className="mobile-daily-lead" onClick={() => report.lead?.entry && navigate(feedArticlePreviewPath(report.lead.entry))}>
              <span>{report.lead.entry?.source_title || "日报头条"} · {displayTime(report.lead.entry?.published_at)}</span>
              <h2>{report.lead.title}</h2>
              <p>{report.lead.summary}</p>
            </button>
          )}

          {sections.map((section) => (
            <section key={section.title} className="mobile-daily-section">
              <h2>{section.title}</h2>
              {section.summary && <p className="mobile-daily-section-summary">{section.summary}</p>}
              <div className="mobile-daily-entry-list">
                {section.items.map((item, index) => (
                  <button
                    type="button"
                    key={`${section.title}-${item.entry_id ?? index}-${item.title}`}
                    className="mobile-daily-entry"
                    onClick={() => item.entry && navigate(feedArticlePreviewPath(item.entry))}
                    disabled={!item.entry}
                  >
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.summary}</p>
                      {item.entry && <em>{item.entry.source_title} · {displayTime(item.entry.published_at)}</em>}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ))}

          <button type="button" className="mobile-secondary-btn mobile-regenerate-btn" disabled={generating} onClick={() => void generate(true)}>
            {generating ? "重新生成中…" : "重新生成这天日报"}
          </button>
        </article>
      )}
    </section>
  );
}

function MobileItemList({ items, emptyText }: { items: ApiItemSummary[]; emptyText: string }) {
  return (
    <div className="mobile-item-list">
      {items.length === 0 && <div className="mobile-empty">{emptyText}</div>}
      {items.map((item) => (
        <Link key={item.id} to={`/items/${item.id}?from=${item.is_inbox ? "inbox" : "library"}`} className="mobile-item-row">
          <div className="mobile-item-body">
            <div className="mobile-item-meta">
              <span>{itemTypeLabel(item.content_type)}</span>
              <span>{statusLabel(item.status)}</span>
              <span>{displayTime(item.updated_at || item.created_at)}</span>
            </div>
            <h3>{item.title || compactSource(item.source_url)}</h3>
            <p>{compactSource(item.source_url)}</p>
            <div className="mobile-item-footer">
              <span>{item.folder_name}</span>
              <span>{item.is_read ? "已读" : "未读"}</span>
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}

function MobileInboxItemRow({
  item,
  folders,
  busy,
  onMove,
  onDelete,
}: {
  item: ApiItemSummary;
  folders: { id: string; name: string }[];
  busy: boolean;
  onMove: (item: ApiItemSummary, folderId: string) => void;
  onDelete: (item: ApiItemSummary) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <>
      <div className="mobile-item-row mobile-inbox-row">
        <Link to={`/items/${item.id}?from=inbox`} className="mobile-item-link">
          <div className="mobile-item-body">
            <div className="mobile-item-meta">
              <span>{itemTypeLabel(item.content_type)}</span>
              <span>{statusLabel(item.status)}</span>
              <span>{displayTime(item.updated_at || item.created_at)}</span>
            </div>
            <h3>{item.title || compactSource(item.source_url)}</h3>
            <p>{compactSource(item.source_url)}</p>
            <div className="mobile-item-footer">
              <span>{item.folder_name}</span>
              <span>{item.is_read ? "已读" : "未读"}</span>
            </div>
          </div>
        </Link>
        <button type="button" className="mobile-row-more-btn" aria-label="更多操作" onClick={() => setMenuOpen(true)}>
          <MobileIcon name="more_horiz" />
        </button>
      </div>
      {menuOpen && (
        <div className="mobile-sheet-backdrop" onClick={() => setMenuOpen(false)}>
          <div className="mobile-action-sheet" role="menu" onClick={(event) => event.stopPropagation()}>
            <div className="mobile-sheet-grabber" />
            <h2>{item.title || "内容操作"}</h2>
            {folders.length > 0 ? (
              <div className="mobile-action-section">
                <span>收藏到知识库</span>
                {folders.map((folder) => (
                  <button
                    key={folder.id}
                    type="button"
                    className="mobile-action-row"
                    disabled={busy}
                    onClick={() => {
                      setMenuOpen(false);
                      onMove(item, folder.id);
                    }}
                  >
                    <MobileIcon name="folder" />
                    <span>{folder.name}</span>
                  </button>
                ))}
              </div>
            ) : (
              <Link className="mobile-action-row" to="/library" onClick={() => setMenuOpen(false)}>
                <MobileIcon name="create_new_folder" />
                <span>先创建文件夹</span>
              </Link>
            )}
            {item.source_url && (
              <a className="mobile-action-row" href={item.source_url} target="_blank" rel="noreferrer">
                <MobileIcon name="open_in_new" />
                <span>打开原文</span>
              </a>
            )}
            <button
              type="button"
              className="mobile-action-row danger"
              disabled={busy}
              onClick={() => {
                setMenuOpen(false);
                onDelete(item);
              }}
            >
              <MobileIcon name="delete" />
              <span>删除</span>
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function MobileInboxPage() {
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [searchParams] = useSearchParams();
  const keyword = searchParams.get("q")?.trim() ?? "";
  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const inboxId = workspace?.default_inbox_folder?.id;
  const customFolders = folders.filter((folder) => !folder.is_builtin && folder.id !== inboxId);

  async function loadInbox() {
    const response = await client.listItems({ inboxOnly: true, keyword: keyword || undefined, pageSize: 100 });
    setItems(response.items);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client.listItems({ inboxOnly: true, keyword: keyword || undefined, pageSize: 100 })
      .then((response) => {
        if (!cancelled) setItems(response.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [client, keyword]);

  async function moveToFolder(item: ApiItemSummary, folderId: string) {
    setBusyItemId(item.id);
    try {
      const result = await client.moveItem(item.id, folderId);
      await loadInbox();
      await loadFolders();
      dispatchToast(`已收藏到知识库：${result.folder_name}`, "success");
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "收藏失败", "error");
    } finally {
      setBusyItemId(null);
    }
  }

  async function deleteItem(item: ApiItemSummary) {
    const confirmed = window.confirm(`确定将「${item.title}」移入最近删除吗？内容会保留 7 天。`);
    if (!confirmed) return;
    setBusyItemId(item.id);
    try {
      await client.deleteItem(item.id);
      await loadInbox();
      await loadFolders();
      dispatchToast("已移入最近删除", "success");
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "删除失败", "error");
    } finally {
      setBusyItemId(null);
    }
  }

  const visibleItems = filter === "unread" ? items.filter((item) => !item.is_read) : items;

  return (
    <section className="mobile-screen">
      <div className="mobile-section-title">
        <p>Read Later</p>
        <h1>稍后阅读</h1>
      </div>
      <div className="mobile-segmented">
        <button type="button" className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部</button>
        <button type="button" className={filter === "unread" ? "active" : ""} onClick={() => setFilter("unread")}>未读</button>
      </div>
      {loading ? (
        <div className="mobile-empty">正在加载稍后阅读…</div>
      ) : (
        <div className="mobile-item-list">
          {visibleItems.length === 0 && <div className="mobile-empty">这里还没有待读内容</div>}
          {visibleItems.map((item) => (
            <MobileInboxItemRow
              key={item.id}
              item={item}
              folders={customFolders}
              busy={busyItemId === item.id}
              onMove={(targetItem, folderId) => void moveToFolder(targetItem, folderId)}
              onDelete={(targetItem) => void deleteItem(targetItem)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function flattenFeeds(feeds: Record<string, ApiFeedPreviewResponse>) {
  return Object.entries(feeds)
    .flatMap(([sourceUrl, feed]) => feed.items.map((item) => ({ ...item, sourceUrl, sourceTitle: feed.site_title })))
    .sort((a, b) => Date.parse(b.published_at || "") - Date.parse(a.published_at || ""));
}

function MobileFeedPage() {
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const keyword = (searchParams.get("q") ?? "").trim().toLowerCase();
  const [sources, setSources] = useState<ApiFeedSourceEntry[]>([]);
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("all");
  const [showAddSource, setShowAddSource] = useState(false);
  const [rssUrl, setRssUrl] = useState("");
  const [addingSource, setAddingSource] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function loadState() {
    const state = await client.getFeedState();
    setSources(state.sources);
    setEntries(flattenFeeds(state.feeds));
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client.getFeedState()
      .then((state) => {
        if (cancelled) return;
        setSources(state.sources);
        setEntries(flattenFeeds(state.feeds));
      })
      .catch(() => {
        if (!cancelled) {
          setSources([]);
          setEntries([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [client]);

  async function refresh() {
    setRefreshing(true);
    try {
      await client.refreshFeeds();
      await loadState();
      dispatchToast("订阅源已刷新", "success");
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "刷新失败", "error");
    } finally {
      setRefreshing(false);
    }
  }

  async function addFeedSource() {
    const targetUrl = rssUrl.trim();
    if (!targetUrl) {
      setSourceError("请先粘贴 RSS 源地址。");
      return;
    }
    setAddingSource(true);
    setSourceError(null);
    try {
      const preview = await client.getFeedPreview(targetUrl, 0);
      const state = await client.cacheFeedPreview(preview);
      setSources(state.sources);
      setEntries(flattenFeeds(state.feeds));
      setSelectedSource(preview.source_url);
      setRssUrl("");
      setShowAddSource(false);
      dispatchToast(`已添加订阅源：${preview.site_title || compactSource(preview.source_url)}`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "RSS 读取失败";
      setSourceError(message);
      void client.markFeedSourceError(targetUrl, message).catch(() => {
        // The visible error is enough for the mobile add flow.
      });
    } finally {
      setAddingSource(false);
    }
  }

  const sourceStats = sources.map((source) => {
    const sourceEntries = entries.filter((entry) => entry.sourceUrl === source.source_url);
    const latestEntry = sourceEntries[0];
    return { ...source, entryCount: sourceEntries.length, latestEntry };
  });
  const selectedSourceTitle = selectedSource === "all"
    ? "全部订阅"
    : sources.find((source) => source.source_url === selectedSource)?.site_title || compactSource(selectedSource);
  const visibleEntries = entries.filter((entry) => {
    if (selectedSource !== "all" && entry.sourceUrl !== selectedSource) return false;
    if (!keyword) return true;
    return `${entry.title} ${entry.summary ?? ""} ${entry.sourceTitle}`.toLowerCase().includes(keyword);
  });

  return (
    <section className="mobile-screen">
      <div className="mobile-section-title mobile-title-row">
        <div>
          <h1>订阅</h1>
          <span className="mobile-feed-count">{sources.length} 个来源 · {entries.length} 篇更新</span>
        </div>
        <div className="mobile-title-actions">
          <button type="button" className="mobile-topbar-btn" aria-label="新增订阅源" onClick={() => { setShowAddSource(true); setSourceError(null); }}>
            <MobileIcon name="add" />
          </button>
          <button type="button" className="mobile-secondary-btn" disabled={refreshing} onClick={() => void refresh()}>
            {refreshing ? "刷新中" : "刷新"}
          </button>
        </div>
      </div>
      {loading ? (
        <div className="mobile-empty">正在加载订阅更新…</div>
      ) : (
        <>
          <div className="mobile-source-strip mobile-feed-filter-rail">
            <button type="button" className={`mobile-source-chip ${selectedSource === "all" ? "active" : ""}`} onClick={() => setSelectedSource("all")}>
              <span>全部</span>
              <em>{entries.length}</em>
            </button>
            {sourceStats.map((source) => (
              <button key={source.source_url} type="button" className={`mobile-source-chip ${selectedSource === source.source_url ? "active" : ""}`} onClick={() => setSelectedSource(source.source_url)}>
                <span>{source.site_title || compactSource(source.source_url)}</span>
                <em>{source.entryCount}</em>
              </button>
            ))}
          </div>

          <div className="mobile-library-header mobile-feed-heading">
            <strong>最新更新</strong>
            <span>{selectedSourceTitle}</span>
          </div>
          <div className="mobile-feed-list mobile-reader-feed-list">
            {visibleEntries.length === 0 && <div className="mobile-empty">还没有订阅更新</div>}
            {visibleEntries.map((entry) => (
              <button key={`${entry.sourceUrl}-${entry.id || entry.link}`} type="button" className="mobile-feed-row" onClick={() => navigate(feedArticlePreviewPath(entry))}>
                <span>{entry.sourceTitle} · {displayTime(entry.published_at)}</span>
                <h3>{entry.title}</h3>
                {entry.summary && <p>{entry.summary}</p>}
              </button>
            ))}
          </div>
        </>
      )}
      {showAddSource && (
        <div className="mobile-sheet-backdrop" onClick={() => setShowAddSource(false)}>
          <div className="mobile-quick-sheet" onClick={(event) => event.stopPropagation()}>
            <h2>新增订阅源</h2>
            <p>粘贴 RSS 地址，添加后会和桌面端使用同一套订阅数据。</p>
            <label>
              <span>RSS 地址</span>
              <input
                value={rssUrl}
                onChange={(event) => setRssUrl(event.target.value)}
                placeholder="https://example.com/feed.xml"
                autoFocus
              />
            </label>
            {sourceError && <div className="mobile-alert">{sourceError}</div>}
            <div className="mobile-sheet-actions">
              <button type="button" className="mobile-primary-btn" disabled={addingSource} onClick={() => void addFeedSource()}>
                {addingSource ? "读取中" : "添加并查看"}
              </button>
              <button type="button" className="mobile-text-btn" disabled={addingSource} onClick={() => setShowAddSource(false)}>取消</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function MobileLibraryPage() {
  const params = useParams();
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const keyword = searchParams.get("q")?.trim() ?? "";
  const [localQuery, setLocalQuery] = useState(keyword);
  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [folderBusy, setFolderBusy] = useState(false);
  const inboxId = workspace?.default_inbox_folder?.id;
  const customFolders = folders.filter((folder) => !folder.is_builtin && folder.id !== inboxId);
  const selectedFolderId = params.folderId;
  const selectedFolder = folders.find((folder) => folder.id === selectedFolderId);
  const isFolderDetail = Boolean(selectedFolderId);
  const filteredFolders = customFolders.filter((folder) => !localQuery || folder.name.toLowerCase().includes(localQuery.toLowerCase()));

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    let cancelled = false;
    if (!selectedFolderId && !localQuery) {
      setItems([]);
      setLoading(false);
      return () => { cancelled = true; };
    }
    setLoading(true);
    client.listItems({ folderId: selectedFolderId, keyword: localQuery || undefined, pageSize: 100 })
      .then((response) => {
        if (!cancelled) setItems(response.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [client, localQuery, selectedFolderId]);

  async function createFolder(event: FormEvent) {
    event.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;
    setFolderBusy(true);
    try {
      const folder = await client.createFolder(name);
      await loadFolders();
      setNewFolderName("");
      setCreatingFolder(false);
      navigate(`/folders/${folder.id}`);
      dispatchToast(`已创建文件夹：${folder.name}`, "success");
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "创建文件夹失败", "error");
    } finally {
      setFolderBusy(false);
    }
  }

  return (
    <section className="mobile-screen">
      <div className="mobile-section-title mobile-title-row">
        <div>
          <p>Library</p>
          <h1>{selectedFolder?.name || "知识库"}</h1>
        </div>
        {isFolderDetail ? (
          <button type="button" className="mobile-secondary-btn" onClick={() => navigate("/library")}>返回</button>
        ) : (
          <button type="button" className="mobile-icon-action-btn" aria-label="新建文件夹" onClick={() => setCreatingFolder(true)}>
            <MobileIcon name="create_new_folder" />
          </button>
        )}
      </div>
      <label className="mobile-library-search" aria-label="搜索知识库">
        <MobileIcon name="search" />
        <input
          value={localQuery}
          onChange={(event) => setLocalQuery(event.target.value)}
          placeholder={isFolderDetail ? "搜索这个文件夹" : "搜索文件夹或内容"}
        />
      </label>
      {!isFolderDetail && (
        <div className="mobile-library-home">
          {localQuery && (
            <div className="mobile-library-header">
              <strong>内容匹配</strong>
              <span>{items.length} 条</span>
            </div>
          )}
          {localQuery && (loading ? <div className="mobile-empty">正在搜索知识库…</div> : <MobileItemList items={items} emptyText="没有匹配内容" />)}

          <div className="mobile-library-header">
            <strong>文件夹</strong>
            <span>{filteredFolders.length} 个</span>
          </div>
          <div className="mobile-folder-list">
            {filteredFolders.length === 0 && (
              <div className="mobile-empty">
                {customFolders.length === 0 ? "还没有文件夹，先创建一个用于整理内容。" : "没有匹配的文件夹。"}
              </div>
            )}
            {filteredFolders.map((folder) => (
              <Link key={folder.id} to={`/folders/${folder.id}`} className="mobile-folder-row">
                <span className="mobile-folder-row-icon"><MobileIcon name="folder" /></span>
                <div>
                  <strong>{folder.name}</strong>
                  <span>{folder.item_count} 条内容</span>
                </div>
                <MobileIcon name="chevron_right" />
              </Link>
            ))}
          </div>
        </div>
      )}
      {isFolderDetail && (
        <>
          <div className="mobile-library-header">
            <strong>内容</strong>
            <span>{items.length} 条</span>
          </div>
          {loading ? <div className="mobile-empty">正在加载知识库…</div> : <MobileItemList items={items} emptyText="这个文件夹还没有内容" />}
        </>
      )}
      {creatingFolder && (
        <div className="mobile-sheet-backdrop" onClick={() => !folderBusy && setCreatingFolder(false)}>
          <form className="mobile-quick-sheet" onSubmit={(event) => void createFolder(event)} onClick={(event) => event.stopPropagation()}>
            <div className="mobile-sheet-grabber" />
            <h2>新建文件夹</h2>
            <input
              className="mobile-sheet-input"
              value={newFolderName}
              onChange={(event) => setNewFolderName(event.target.value)}
              placeholder="文件夹名称"
              autoFocus
            />
            <div className="mobile-sheet-actions">
              <button type="button" className="mobile-secondary-btn" disabled={folderBusy} onClick={() => setCreatingFolder(false)}>取消</button>
              <button type="submit" className="mobile-primary-btn" disabled={folderBusy || !newFolderName.trim()}>
                {folderBusy ? "创建中" : "创建"}
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function providerCapabilityLabel(provider: ApiProvider) {
  return capabilityOfProvider(provider) === "asr" ? "转写" : "大语言模型";
}

function providerModelLabel(provider: ApiProvider) {
  return provider.chat_model || provider.embedding_model || provider.transcription_model || "未填写模型";
}

function providerTypeLabel(type: string) {
  if (type === "openai_compatible") return "OpenAI 兼容";
  if (type === "doubao") return "豆包";
  if (type === "deepseek") return "DeepSeek";
  if (type === "custom") return "自定义";
  return type || "Custom";
}

function capabilityOfProvider(provider: ApiProvider): ProviderCapability {
  if (provider.capability === "asr" || provider.capability === "llm") return provider.capability;
  if ((provider.transcription_model || provider.transcription_app_id) && !provider.chat_model) return "asr";
  return "llm";
}

function defaultInputCapabilities(capability: ProviderCapability): ModelInputCapability[] {
  return capability === "asr" ? ["audio"] : ["text"];
}

function normalizeInputCapabilities(value: Array<string> | undefined, capability: ProviderCapability): ModelInputCapability[] {
  const selected = new Set(value?.filter((item): item is ModelInputCapability => (
    item === "text" || item === "image" || item === "audio" || item === "video"
  )));
  const normalized = modelInputCapabilityOptions.map((option) => option.value).filter((value) => selected.has(value));
  return normalized.length ? normalized : defaultInputCapabilities(capability);
}

function inputCapabilityLabels(value: Array<string> | undefined, capability: ProviderCapability) {
  return normalizeInputCapabilities(value, capability).map((item) => modelInputCapabilityOptions.find((option) => option.value === item)?.label ?? item);
}

function emptyProviderForm(capability: ProviderCapability): ProviderFormState {
  return {
    id: null,
    capability,
    input_capabilities: defaultInputCapabilities(capability),
    provider_name: capability === "llm" ? "Doubao LLM" : "Doubao ASR",
    provider_type: "doubao",
    base_url: capability === "llm" ? DOUBAO_BASE_URL : "",
    api_key: "",
    chat_model: "",
    transcription_model: capability === "asr" ? "volc.bigasr.auc_turbo" : "",
    transcription_app_id: "",
    transcription_access_token: "",
    transcription_secret_key: "",
    thinking_mode: "default",
  };
}

function providerToForm(provider: ApiProvider): ProviderFormState {
  const capability = capabilityOfProvider(provider);
  return {
    id: provider.id,
    capability,
    input_capabilities: normalizeInputCapabilities(provider.input_capabilities, capability),
    provider_name: provider.provider_name,
    provider_type: (provider.provider_type as ProviderKind | undefined) ?? "custom",
    base_url: provider.base_url ?? "",
    api_key: "",
    chat_model: provider.chat_model ?? "",
    transcription_model: provider.transcription_model ?? "",
    transcription_app_id: provider.transcription_app_id ?? "",
    transcription_access_token: "",
    transcription_secret_key: "",
    thinking_mode: provider.thinking_mode === "enabled" || provider.thinking_mode === "disabled" ? provider.thinking_mode : "default",
  };
}

function applyProviderDefaults(form: ProviderFormState, providerType: ProviderKind): ProviderFormState {
  if (providerType === "deepseek") {
    return {
      ...form,
      provider_type: "deepseek",
      provider_name: form.provider_name && !["Doubao", "Doubao LLM", "DeepSeek", "DeepSeek LLM"].includes(form.provider_name)
        ? form.provider_name
        : "DeepSeek LLM",
      base_url: form.capability === "llm" && (!form.base_url || form.base_url === DOUBAO_BASE_URL) ? DEEPSEEK_BASE_URL : form.base_url,
      chat_model: form.capability === "llm" ? form.chat_model : "",
      transcription_model: "",
      thinking_mode: form.thinking_mode,
    };
  }
  if (providerType !== "doubao") {
    return {
      ...form,
      provider_type: providerType,
      base_url: form.capability === "llm" ? form.base_url : "",
      chat_model: form.capability === "llm" ? form.chat_model : "",
      transcription_model: form.capability === "asr" ? form.transcription_model : "",
      thinking_mode: form.thinking_mode,
    };
  }
  return {
    ...form,
    provider_type: "doubao",
    provider_name: form.provider_name && !["Doubao", "Doubao LLM", "Doubao ASR"].includes(form.provider_name)
      ? form.provider_name
      : form.capability === "llm" ? "Doubao LLM" : "Doubao ASR",
    base_url: form.capability === "llm" && (!form.base_url || form.base_url === DEEPSEEK_BASE_URL) ? DOUBAO_BASE_URL : form.base_url,
    chat_model: form.capability === "llm" ? form.chat_model : "",
    transcription_model: form.capability === "asr" ? (form.transcription_model || "volc.bigasr.auc_turbo") : "",
  };
}

function providerCredentialConfigured(provider: ApiProvider | undefined, capability: ProviderCapability, field: "api_key" | "access_token" | "secret_key") {
  if (!provider) return false;
  if (capability === "llm" && field === "api_key") return Boolean(provider.api_key_configured);
  if (capability === "asr" && field === "access_token") return Boolean(provider.transcription_access_token_configured);
  if (capability === "asr" && field === "secret_key") return Boolean(provider.transcription_secret_key_configured);
  return false;
}

function thinkingModeLabel(mode: string | undefined) {
  if (mode === "enabled") return "思考：开启";
  if (mode === "disabled") return "思考：关闭";
  return "思考：默认";
}

function MobileModelServices({
  apiBaseUrl,
  providers,
  onRefresh,
}: {
  apiBaseUrl: string;
  providers: ApiProvider[];
  onRefresh: () => Promise<ApiProvider[]>;
}) {
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [expanded, setExpanded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [activeCapability, setActiveCapability] = useState<ProviderCapability>("llm");
  const [editing, setEditing] = useState<ProviderCapability | null>(null);
  const [llmForm, setLlmForm] = useState<ProviderFormState>(() => emptyProviderForm("llm"));
  const [asrForm, setAsrForm] = useState<ProviderFormState>(() => emptyProviderForm("asr"));
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const llmProviders = providers.filter((provider) => capabilityOfProvider(provider) === "llm");
  const asrProviders = providers.filter((provider) => capabilityOfProvider(provider) === "asr");
  const activeProviders = activeCapability === "llm" ? llmProviders : asrProviders;
  const activeForm = activeCapability === "llm" ? llmForm : asrForm;
  const setActiveForm = activeCapability === "llm" ? setLlmForm : setAsrForm;
  const currentLlm = llmProviders.find((provider) => provider.is_enabled) ?? llmProviders[0];
  const currentAsr = asrProviders.find((provider) => provider.is_enabled) ?? asrProviders[0];

  async function refresh() {
    setRefreshing(true);
    try {
      await onRefresh();
      dispatchToast("模型服务已刷新", "success");
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "模型服务刷新失败", "error");
    } finally {
      setRefreshing(false);
    }
  }

  async function saveProvider(form: ProviderFormState) {
    const existingProvider = providers.find((provider) => provider.id === form.id);
    const name = form.provider_name.trim() || (form.capability === "llm" ? "大语言模型" : "转写模型");
    const baseUrl = form.base_url.trim();
    const apiKey = form.api_key.trim();
    const chatModel = form.chat_model.trim();
    const transcriptionAppId = form.transcription_app_id.trim();
    const transcriptionModel = form.transcription_model.trim();
    const transcriptionAccessToken = form.transcription_access_token.trim();
    const transcriptionSecretKey = form.transcription_secret_key.trim();

    if (form.capability === "llm") {
      if (!baseUrl) {
        setError("大语言模型需要填写 BaseURL。");
        return;
      }
      if (!chatModel) {
        setError("大语言模型需要填写模型名或 Endpoint。");
        return;
      }
      if (!apiKey && !providerCredentialConfigured(existingProvider, "llm", "api_key")) {
        setError("大语言模型需要填写 API Key。");
        return;
      }
    } else {
      if (!transcriptionAppId) {
        setError("ASR 模型需要填写 APP ID。");
        return;
      }
      if (!transcriptionModel) {
        setError("ASR 模型需要填写资源 ID。");
        return;
      }
      if (!transcriptionAccessToken && !providerCredentialConfigured(existingProvider, "asr", "access_token")) {
        setError("ASR 模型需要填写 Access Token。");
        return;
      }
      if (!transcriptionSecretKey && !providerCredentialConfigured(existingProvider, "asr", "secret_key")) {
        setError("ASR 模型需要填写 Secret Key。");
        return;
      }
    }

    setSaving(true);
    setError(null);
    try {
      await (form.id ? client.updateProvider(form.id, {
        provider_name: name,
        provider_type: form.provider_type,
        capability: form.capability,
        input_capabilities: normalizeInputCapabilities(form.input_capabilities, form.capability),
        base_url: form.capability === "llm" ? baseUrl : null,
        api_key: form.capability === "llm" ? apiKey || null : null,
        chat_model: form.capability === "llm" ? chatModel : null,
        embedding_model: null,
        transcription_model: form.capability === "asr" ? transcriptionModel : null,
        transcription_app_id: form.capability === "asr" ? transcriptionAppId : null,
        transcription_access_token: form.capability === "asr" ? transcriptionAccessToken || null : null,
        transcription_secret_key: form.capability === "asr" ? transcriptionSecretKey || null : null,
        thinking_mode: form.capability === "llm" ? form.thinking_mode : null,
        is_enabled: true,
      }) : client.createProvider({
        provider_name: name,
        provider_type: form.provider_type,
        capability: form.capability,
        input_capabilities: normalizeInputCapabilities(form.input_capabilities, form.capability),
        base_url: form.capability === "llm" ? baseUrl : null,
        api_key: form.capability === "llm" ? apiKey || null : null,
        chat_model: form.capability === "llm" ? chatModel : null,
        embedding_model: null,
        transcription_model: form.capability === "asr" ? transcriptionModel : null,
        transcription_app_id: form.capability === "asr" ? transcriptionAppId : null,
        transcription_access_token: form.capability === "asr" ? transcriptionAccessToken || null : null,
        transcription_secret_key: form.capability === "asr" ? transcriptionSecretKey || null : null,
        thinking_mode: form.capability === "llm" ? form.thinking_mode : null,
        is_enabled: true,
      }));
      await onRefresh();
      setEditing(null);
      setLlmForm(emptyProviderForm("llm"));
      setAsrForm(emptyProviderForm("asr"));
      dispatchToast(form.capability === "llm" ? "大语言模型已保存" : "转写模型已保存", "success");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "保存模型失败");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProvider(providerId: string) {
    setSaving(true);
    setError(null);
    try {
      await client.deleteProvider(providerId);
      await onRefresh();
      dispatchToast("模型配置已删除", "success");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "删除模型失败");
    } finally {
      setSaving(false);
    }
  }

  async function activateProvider(provider: ApiProvider) {
    const capability = capabilityOfProvider(provider);
    setSaving(true);
    setError(null);
    try {
      await client.updateProvider(provider.id, {
        provider_name: provider.provider_name,
        provider_type: provider.provider_type as ProviderKind,
        capability,
        input_capabilities: normalizeInputCapabilities(provider.input_capabilities, capability),
        base_url: capability === "llm" ? provider.base_url ?? null : null,
        api_key: null,
        chat_model: capability === "llm" ? provider.chat_model ?? null : null,
        embedding_model: null,
        transcription_model: capability === "asr" ? provider.transcription_model ?? null : null,
        transcription_app_id: capability === "asr" ? provider.transcription_app_id ?? null : null,
        transcription_access_token: null,
        transcription_secret_key: null,
        thinking_mode: capability === "llm" ? provider.thinking_mode ?? "default" : null,
        is_enabled: true,
      });
      await onRefresh();
      dispatchToast(capability === "llm" ? "已切换当前大语言模型" : "已切换当前转写模型", "success");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "切换模型失败");
    } finally {
      setSaving(false);
    }
  }

  async function testProvider(provider: ApiProvider) {
    setTestingId(provider.id);
    setError(null);
    try {
      const result = await client.testProvider(provider.id);
      await onRefresh();
      if (result.ok) dispatchToast(result.message || `模型测试通过，耗时 ${result.latency_ms} ms`, "success");
      else setError(result.message || "模型测试失败。");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "模型测试失败");
    } finally {
      setTestingId(null);
    }
  }

  function beginCreate(capability: ProviderCapability) {
    setActiveCapability(capability);
    if (capability === "llm") setLlmForm(emptyProviderForm("llm"));
    else setAsrForm(emptyProviderForm("asr"));
    setEditing(capability);
    setError(null);
  }

  function beginEdit(provider: ApiProvider) {
    const capability = capabilityOfProvider(provider);
    const form = providerToForm(provider);
    setActiveCapability(capability);
    if (capability === "llm") setLlmForm(form);
    else setAsrForm(form);
    setEditing(capability);
    setError(null);
  }

  return (
    <div className="mobile-setting-card mobile-model-card">
      <div className="mobile-setting-line">
        <span>模型服务</span>
        <button type="button" className="mobile-text-btn" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起" : "管理"}
        </button>
      </div>
      <div className="mobile-model-summary">
        <div className="mobile-model-summary-row">
          <div className="mobile-provider-icon">
            <MobileIcon name="neurology" />
          </div>
          <div>
            <strong>大语言模型</strong>
            <span>{currentLlm ? `${currentLlm.provider_name} · ${providerModelLabel(currentLlm)}` : "未配置"}</span>
          </div>
          <em>{currentLlm?.is_enabled ? "当前" : currentLlm ? "可用" : "缺失"}</em>
        </div>
        <div className="mobile-model-summary-row">
          <div className="mobile-provider-icon">
            <MobileIcon name="graphic_eq" />
          </div>
          <div>
            <strong>ASR 转写</strong>
            <span>{currentAsr ? `${currentAsr.provider_name} · ${providerModelLabel(currentAsr)}` : "未配置"}</span>
          </div>
          <em>{currentAsr?.is_enabled ? "当前" : currentAsr ? "可用" : "缺失"}</em>
        </div>
      </div>
      {expanded && (
        <>
          <div className="mobile-segmented mobile-provider-tabs">
            <button type="button" className={activeCapability === "llm" ? "active" : ""} onClick={() => setActiveCapability("llm")}>大语言模型</button>
            <button type="button" className={activeCapability === "asr" ? "active" : ""} onClick={() => setActiveCapability("asr")}>ASR 转写</button>
          </div>
          <div className="mobile-provider-list">
            {activeProviders.length === 0 && <div className="mobile-empty slim">{activeCapability === "llm" ? "还没有大语言模型" : "还没有转写模型"}</div>}
            {activeProviders.map((provider) => (
              <div key={provider.id} className={`mobile-provider-row ${provider.is_enabled ? "active" : ""}`}>
                <div className="mobile-provider-icon">
                  <MobileIcon name={capabilityOfProvider(provider) === "asr" ? "graphic_eq" : "neurology"} />
                </div>
                <div>
                  <strong>{provider.provider_name}</strong>
                  <span>{providerCapabilityLabel(provider)} · {providerTypeLabel(provider.provider_type)}</span>
                  <em>{providerModelLabel(provider)}</em>
                  <p>{inputCapabilityLabels(provider.input_capabilities, capabilityOfProvider(provider)).join(" / ")}{capabilityOfProvider(provider) === "llm" ? ` · ${thinkingModeLabel(provider.thinking_mode)}` : ""}</p>
                </div>
                <span className={`mobile-provider-status ${provider.is_enabled ? "active" : ""}`}>
                  {provider.is_enabled ? "当前" : "停用"}
                </span>
                <div className="mobile-provider-actions">
                  {!provider.is_enabled && (
                    <button type="button" className="mobile-text-btn" disabled={saving} onClick={() => void activateProvider(provider)}>设为当前</button>
                  )}
                  {capabilityOfProvider(provider) === "llm" && (
                    <button type="button" className="mobile-text-btn" disabled={testingId === provider.id || saving} onClick={() => void testProvider(provider)}>
                      {testingId === provider.id ? "测试中" : "测试"}
                    </button>
                  )}
                  <button type="button" className="mobile-text-btn" disabled={saving} onClick={() => beginEdit(provider)}>编辑</button>
                  <button type="button" className="mobile-text-btn mobile-danger-text-btn" disabled={saving} onClick={() => void deleteProvider(provider.id)}>删除</button>
                </div>
              </div>
            ))}
          </div>
          {editing === activeCapability && (
            <MobileProviderEditor
              form={activeForm}
              providers={providers}
              saving={saving}
              onCancel={() => setEditing(null)}
              onChange={setActiveForm}
              onSave={() => void saveProvider(activeForm)}
            />
          )}
          {error && <div className="mobile-alert">{error}</div>}
          <div className="mobile-setting-actions">
            <button type="button" className="mobile-secondary-btn" onClick={() => beginCreate(activeCapability)}>
              添加{activeCapability === "llm" ? "大语言模型" : "ASR"}
            </button>
            <button type="button" className="mobile-secondary-btn" disabled={refreshing} onClick={() => void refresh()}>
              {refreshing ? "刷新中" : "刷新状态"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function MobileProviderEditor({
  form,
  providers,
  saving,
  onCancel,
  onChange,
  onSave,
}: {
  form: ProviderFormState;
  providers: ApiProvider[];
  saving: boolean;
  onCancel: () => void;
  onChange: (updater: (current: ProviderFormState) => ProviderFormState) => void;
  onSave: () => void;
}) {
  const isAsr = form.capability === "asr";
  const existingProvider = providers.find((provider) => provider.id === form.id);
  return (
    <div className="mobile-provider-editor">
      <div className="mobile-setting-line">
        <strong>{form.id ? "编辑模型配置" : "添加模型配置"}</strong>
        <button type="button" className="mobile-text-btn" onClick={onCancel}>收起</button>
      </div>
      <label>
        <span>供应商</span>
        <select value={form.provider_type} onChange={(event) => onChange((current) => applyProviderDefaults(current, event.target.value as ProviderKind))}>
          <option value="doubao">豆包</option>
          <option value="deepseek" disabled={isAsr}>DeepSeek</option>
          <option value="openai_compatible" disabled={isAsr}>OpenAI 兼容</option>
          <option value="custom" disabled={isAsr}>自定义</option>
        </select>
      </label>
      <label>
        <span>自定义名称</span>
        <input value={form.provider_name} onChange={(event) => onChange((current) => ({ ...current, provider_name: event.target.value }))} />
      </label>
      <div>
        <span>输入能力</span>
        <div className="mobile-checkbox-grid">
          {modelInputCapabilityOptions.map((option) => (
            <label key={option.value} className="mobile-checkbox-row">
              <input
                type="checkbox"
                checked={form.input_capabilities.includes(option.value)}
                onChange={(event) => onChange((current) => {
                  const selected = new Set(current.input_capabilities);
                  if (event.target.checked) selected.add(option.value);
                  else selected.delete(option.value);
                  return { ...current, input_capabilities: normalizeInputCapabilities(Array.from(selected), current.capability) };
                })}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </div>
      {!isAsr && (
        <>
          <label>
            <span>BaseURL</span>
            <input value={form.base_url} onChange={(event) => onChange((current) => ({ ...current, base_url: event.target.value }))} placeholder={form.provider_type === "doubao" ? DOUBAO_BASE_URL : form.provider_type === "deepseek" ? DEEPSEEK_BASE_URL : "https://example.com/v1"} />
          </label>
          <label>
            <span>API Key</span>
            <input type="password" value={form.api_key} onChange={(event) => onChange((current) => ({ ...current, api_key: event.target.value }))} placeholder={existingProvider?.api_key_configured ? "已保存，留空沿用" : "填入 API Key"} />
          </label>
          <label>
            <span>模型名 / Endpoint</span>
            <input value={form.chat_model} onChange={(event) => onChange((current) => ({ ...current, chat_model: event.target.value }))} placeholder={form.provider_type === "doubao" ? "ep-..." : form.provider_type === "deepseek" ? "deepseek-chat" : "模型名"} />
          </label>
          <div>
            <span>思考模式</span>
            <div className="mobile-segmented mobile-provider-tabs">
              {(["default", "enabled", "disabled"] as const).map((mode) => (
                <button key={mode} type="button" className={form.thinking_mode === mode ? "active" : ""} onClick={() => onChange((current) => ({ ...current, thinking_mode: mode }))}>
                  {mode === "default" ? "默认" : mode === "enabled" ? "开启" : "关闭"}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
      {isAsr && (
        <>
          <label>
            <span>APP ID</span>
            <input value={form.transcription_app_id} onChange={(event) => onChange((current) => ({ ...current, transcription_app_id: event.target.value }))} />
          </label>
          <label>
            <span>资源 ID</span>
            <input value={form.transcription_model} onChange={(event) => onChange((current) => ({ ...current, transcription_model: event.target.value }))} placeholder="volc.bigasr.auc_turbo" />
          </label>
          <label>
            <span>Access Token</span>
            <input type="password" value={form.transcription_access_token} onChange={(event) => onChange((current) => ({ ...current, transcription_access_token: event.target.value }))} placeholder={existingProvider?.transcription_access_token_configured ? "已保存，留空沿用" : "填入 Access Token"} />
          </label>
          <label>
            <span>Secret Key</span>
            <input type="password" value={form.transcription_secret_key} onChange={(event) => onChange((current) => ({ ...current, transcription_secret_key: event.target.value }))} placeholder={existingProvider?.transcription_secret_key_configured ? "已保存，留空沿用" : "填入 Secret Key"} />
          </label>
        </>
      )}
      <button type="button" className="mobile-primary-btn" disabled={saving} onClick={onSave}>
        {saving ? "保存中" : "保存并设为当前使用"}
      </button>
    </div>
  );
}

function MobileMePage() {
  const {
    apiBaseUrl,
    connectionState,
    currentUser,
    health,
    loadProviders,
    logout,
    providers,
    setThemeMode,
    themeMode,
  } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [bilibili, setBilibili] = useState<ApiBilibiliIntegrationSettings | null>(null);
  const [qrcode, setQrcode] = useState<ApiBilibiliQrcodeGenerateResponse | null>(null);
  const [bilibiliQrState, setBilibiliQrState] = useState<string | null>(null);
  const [bilibiliBusy, setBilibiliBusy] = useState(false);

  useEffect(() => {
    client.getBilibiliIntegration()
      .then(setBilibili)
      .catch(() => setBilibili(null));
  }, [client]);

  useEffect(() => {
    if (!qrcode) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void client.pollBilibiliQrcode(qrcode.qrcode_key)
        .then((result) => {
          if (cancelled) return;
          setBilibiliQrState(result.message);
          if (result.state === "confirmed" && result.saved_cookie) {
            setBilibili(result.saved_cookie);
            setQrcode(null);
            dispatchToast("Bilibili 已验证", "success");
          }
          if (result.state === "expired" || result.state === "failed") {
            setQrcode(null);
            dispatchToast(result.message || "二维码已失效", "error");
          }
        })
        .catch(() => {
          if (!cancelled) setBilibiliQrState("等待扫码确认");
        });
    }, 1800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [client, qrcode]);

  async function startBilibiliQrcode() {
    setBilibiliBusy(true);
    setBilibiliQrState(null);
    try {
      setQrcode(await client.createBilibiliQrcode());
    } catch (error) {
      dispatchToast(error instanceof Error ? error.message : "二维码生成失败", "error");
    } finally {
      setBilibiliBusy(false);
    }
  }

  return (
    <section className="mobile-screen">
      <div className="mobile-section-title">
        <p>Account</p>
        <h1>我</h1>
      </div>

      <div className="mobile-settings-group">
        <div className="mobile-account-card">
          <div className="mobile-avatar">{currentUser?.username?.slice(0, 1).toUpperCase() || "O"}</div>
          <div>
            <strong>{currentUser?.username || "未登录"}</strong>
            <span>{currentUser?.email || "私有部署账号"}</span>
          </div>
          {currentUser && (
            <button type="button" className="mobile-text-btn" onClick={logout}>退出</button>
          )}
        </div>

        <div className="mobile-setting-card">
          <div className="mobile-setting-line">
            <span>服务状态</span>
            <strong>{connectionState === "connected" ? "已连接" : "未连接"}</strong>
          </div>
          <span>{health?.version ? `版本 ${health.version}` : "服务器地址由部署环境配置"}</span>
        </div>

        <div className="mobile-setting-card mobile-bilibili-card">
          <div className="mobile-setting-line">
            <span>Bilibili 验证</span>
            <strong>{bilibili?.ready_for_authenticated_fetch ? "已就绪" : "未配置"}</strong>
          </div>
          {qrcode ? (
            <div className="mobile-qr-panel">
              <QRCodeSVG value={qrcode.url} size={168} level="M" includeMargin />
              <span>{bilibiliQrState || "用 Bilibili App 扫码确认"}</span>
            </div>
          ) : (
            <div className="mobile-setting-line">
              <span>{bilibili?.ready_for_authenticated_fetch ? "需要时可重新扫码更新登录状态" : "扫码后自动写入服务端 Cookie"}</span>
              <button type="button" className="mobile-secondary-btn" disabled={bilibiliBusy} onClick={() => void startBilibiliQrcode()}>
                {bilibiliBusy ? "生成中" : bilibili?.ready_for_authenticated_fetch ? "重新验证" : "扫码验证"}
              </button>
            </div>
          )}
        </div>

        <MobileModelServices apiBaseUrl={apiBaseUrl} providers={providers} onRefresh={loadProviders} />

        <div className="mobile-setting-card">
          <span>外观</span>
          <div className="mobile-segmented">
            {(["system", "light", "dark"] as const).map((mode) => (
              <button key={mode} type="button" className={themeMode === mode ? "active" : ""} onClick={() => setThemeMode(mode)}>
                {mode === "system" ? "系统" : mode === "light" ? "浅色" : "深色"}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function QuickAddSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { apiBaseUrl, loadFolders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeQuickAddUrl(url);
    if (!normalized) {
      setError("请先粘贴链接");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const sourceHint = isBilibiliUrl(normalized) ? "bilibili_video" : "article";
      const result = await client.importItem(normalized, sourceHint);
      await loadFolders();
      setUrl("");
      onClose();
      dispatchToast(result.is_duplicate ? `已存在：${result.uid}` : `已加入稍后阅读：${result.uid}`, result.is_duplicate ? "info" : "success");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "导入失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mobile-sheet-backdrop" onClick={onClose}>
      <form className="mobile-quick-sheet" onSubmit={(event) => void submit(event)} onClick={(event) => event.stopPropagation()}>
        <div className="mobile-sheet-grabber" />
        <h2>导入链接</h2>
        <p>Bilibili 链接会按视频处理，其他链接按文章处理，结果统一进入稍后阅读。</p>
        <textarea value={url} onChange={(event) => setUrl(event.target.value)} placeholder="粘贴文章、Bilibili 或播客链接" rows={4} autoFocus />
        {error && <div className="mobile-alert">{error}</div>}
        <div className="mobile-sheet-actions">
          <button type="button" className="mobile-secondary-btn" onClick={onClose}>取消</button>
          <button type="submit" className="mobile-primary-btn" disabled={busy}>{busy ? "导入中…" : "导入"}</button>
        </div>
      </form>
    </div>
  );
}

function MobileToastView({ toast, onClose }: { toast: MobileToast; onClose: () => void }) {
  if (!toast) return null;
  return (
    <button type="button" className={`mobile-toast mobile-toast-${toast.tone}`} onClick={onClose}>
      {toast.message}
    </button>
  );
}

export function MobileApp() {
  const location = useLocation();
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const [toast, setToast] = useState<MobileToast>(null);

  useEffect(() => {
    const handleToast = (event: Event) => {
      const detail = (event as CustomEvent<NonNullable<MobileToast>>).detail;
      if (!detail?.message) return;
      setToast(detail);
      window.setTimeout(() => setToast(null), 2600);
    };
    window.addEventListener("oneradar:toast", handleToast);
    return () => window.removeEventListener("oneradar:toast", handleToast);
  }, []);

  const activeTab = mobileTabFromPath(location.pathname);

  return (
    <div className={`mobile-app mobile-tab-${activeTab}`}>
      {activeTab === "inbox" && <MobileTopBar onAdd={() => setQuickAddOpen(true)} />}
      <main className="mobile-main">
        <Routes>
          <Route path="/" element={<Navigate to="/daily" replace />} />
          <Route path="/daily" element={<MobileDailyPage />} />
          <Route path="/inbox" element={<MobileInboxPage />} />
          <Route path="/feed" element={<MobileFeedPage />} />
          <Route path="/feed/preview" element={<FeedArticlePreviewPage />} />
          <Route path="/library" element={<MobileLibraryPage />} />
          <Route path="/folders/:folderId" element={<MobileLibraryPage />} />
          <Route path="/items/:itemId" element={<ItemDetailPage />} />
          <Route path="/reader/:itemId" element={<ItemDetailPage />} />
          <Route path="/me" element={<MobileMePage />} />
          <Route path="/settings" element={<MobileMePage />} />
          <Route path="*" element={<Navigate to="/daily" replace />} />
        </Routes>
      </main>
      <MobileBottomNav />
      <QuickAddSheet open={quickAddOpen} onClose={() => setQuickAddOpen(false)} />
      <MobileToastView toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
