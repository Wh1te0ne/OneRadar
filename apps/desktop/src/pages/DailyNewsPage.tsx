import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { layout, prepare } from "@chenglou/pretext";
import { useParams, useSearchParams } from "react-router-dom";
import { ApiError, createApiClient } from "../api";
import type { ApiDailyNewsItem, ApiDailyNewsReportResponse } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAppState } from "../state/appState";
import { hasConfiguredLlmProvider } from "../utils/providers";

const DAILY_NEWS_GENERATION_KEY = "oneradar.daily-news.generation";
const DAILY_NEWS_BACKGROUND_SYNC_KEY = "oneradar.daily-news.background-sync";
const DAILY_NEWS_GENERATION_TTL_MS = 12 * 60 * 1000;
const RUNTIME_SHARE_BASE_URL = window.__ONERADAR_CONFIG__?.shareBaseUrl;

function todayDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDate(value: string, deltaDays: number) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return todayDate();
  date.setDate(date.getDate() + deltaDays);
  return dateKey(date);
}

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDate(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfMonth(value: string) {
  const date = parseLocalDate(value) ?? new Date();
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function shiftMonth(value: Date, deltaMonths: number) {
  return new Date(value.getFullYear(), value.getMonth() + deltaMonths, 1);
}

function isSameMonth(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth();
}

function buildCalendarDays(monthDate: Date) {
  const firstDay = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const start = new Date(firstDay);
  start.setDate(firstDay.getDate() - firstDay.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
}

function displayCalendarMonth(value: Date) {
  return value.toLocaleDateString("zh-CN", { year: "numeric", month: "long" });
}

function displayDate(value: string) {
  const date = parseLocalDate(value);
  if (!date) return value;
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function displayYear(value: string) {
  const date = parseLocalDate(value);
  if (!date) return "";
  return `${date.getFullYear()}`;
}

function displayGeneratedAt(value?: string | null) {
  if (!value) return "尚未生成";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${year}/${month}/${day} ${hour}:${minute}`;
}

function displayPublishedAt(value?: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function itemKey(item: ApiDailyNewsItem, fallback: string) {
  return `${item.entry_id ?? item.entry?.id ?? fallback}:${item.title}`;
}

type PendingGeneration = {
  date: string;
  startedAt: string;
  force: boolean;
};

type DailyNewsLayoutClass = "daily-news-layout-compact" | "daily-news-layout-balanced" | "daily-news-layout-spacious";
type DailyNewsHeadlineClass = "daily-news-headline-tight" | "daily-news-headline-balanced" | "daily-news-headline-wide";
type DailyNewsLayoutPlan = {
  pageClass: DailyNewsLayoutClass;
  headlineClass: DailyNewsHeadlineClass;
  sectionClasses: string[];
};

function readPendingGeneration(): PendingGeneration | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(DAILY_NEWS_GENERATION_KEY) || "null") as PendingGeneration | null;
    if (!parsed?.date || !parsed.startedAt) return null;
    if (Date.now() - new Date(parsed.startedAt).getTime() > DAILY_NEWS_GENERATION_TTL_MS) {
      localStorage.removeItem(DAILY_NEWS_GENERATION_KEY);
      return null;
    }
    return parsed;
  } catch {
    localStorage.removeItem(DAILY_NEWS_GENERATION_KEY);
    return null;
  }
}

function writePendingGeneration(pending: PendingGeneration) {
  localStorage.setItem(DAILY_NEWS_GENERATION_KEY, JSON.stringify(pending));
}

function clearPendingGeneration(date?: string) {
  const pending = readPendingGeneration();
  if (!pending || (date && pending.date !== date)) return;
  localStorage.removeItem(DAILY_NEWS_GENERATION_KEY);
}

function isFreshGeneratedReport(report: ApiDailyNewsReportResponse | null, pending: PendingGeneration | null) {
  if (!report || report.status !== "ready" || !pending || report.report_date !== pending.date || !report.generated_at) return false;
  return new Date(report.generated_at).getTime() >= new Date(pending.startedAt).getTime() - 2000;
}

function publicShareBaseUrl() {
  const configured = RUNTIME_SHARE_BASE_URL?.trim().replace(/\/+$/, "");
  return configured || window.location.origin;
}

function shouldKeepDailyNewsPendingAfterError(error: unknown) {
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status === 408 || error.status === 499 || error.status === 504;
}

function measureWrappedLines(text: string, width: number, font: string, lineHeight: number) {
  const value = text.trim();
  if (!value) return 0;
  try {
    return layout(prepare(value, font, { wordBreak: "normal" }), width, lineHeight).lineCount;
  } catch {
    return Math.ceil(value.length / Math.max(16, Math.floor(width / 14)));
  }
}

function pickDailyNewsLayoutClass(width: number, report: ApiDailyNewsReportResponse | null, sections: ApiDailyNewsReportResponse["sections"]): DailyNewsLayoutClass {
  if (!report || width < 760) return "daily-news-layout-compact";
  const columnWidth = width >= 980 ? Math.max(300, (width - 34) / 2) : width;
  const bodyFont = '14px Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif';
  const titleFont = '760 20px Georgia, "Noto Serif SC", serif';
  const leadTitleFont = '760 48px Georgia, "Noto Serif SC", serif';
  const leadTitleLines = measureWrappedLines(report.lead?.title || report.headline || "", Math.min(width, 780), leadTitleFont, 52);
  const leadSummaryLines = measureWrappedLines(report.lead?.summary || report.headline || "", Math.min(420, columnWidth), bodyFont, 24);
  const sectionLines = sections.reduce((total, section) => {
    const headingLines = measureWrappedLines(`${section.title} ${section.summary}`, columnWidth, titleFont, 27);
    const itemLines = section.items.reduce((itemTotal, item) => itemTotal + measureWrappedLines(`${item.title} ${item.summary}`, columnWidth, bodyFont, 24), 0);
    return total + headingLines + itemLines;
  }, 0);

  if (leadTitleLines > 3 || leadSummaryLines > 5 || sectionLines > 92) return "daily-news-layout-compact";
  if (width >= 1080 && sectionLines < 58 && leadTitleLines <= 2) return "daily-news-layout-spacious";
  return "daily-news-layout-balanced";
}

function pickDailyNewsHeadlineClass(width: number, report: ApiDailyNewsReportResponse | null): DailyNewsHeadlineClass {
  if (!report || width < 760) return "daily-news-headline-tight";
  const headline = report.lead?.title || report.headline || "";
  const leadColumnWidth = width >= 980 ? Math.max(420, width * 0.62) : width;
  const looseLines = measureWrappedLines(headline, Math.min(leadColumnWidth, 780), '760 54px Georgia, "Noto Serif SC", serif', 58);
  const balancedLines = measureWrappedLines(headline, Math.min(leadColumnWidth, 650), '760 48px Georgia, "Noto Serif SC", serif', 52);
  if (looseLines <= 2 && width >= 1040) return "daily-news-headline-wide";
  if (balancedLines <= 3) return "daily-news-headline-balanced";
  return "daily-news-headline-tight";
}

function measureDailyNewsSectionLines(section: ApiDailyNewsReportResponse["sections"][number], width: number) {
  const titleFont = '760 26px Georgia, "Noto Serif SC", serif';
  const bodyFont = '14px Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif';
  const headingLines = measureWrappedLines(`${section.title} ${section.summary}`, width, titleFont, 31);
  const itemLines = section.items.reduce((total, item) => total + measureWrappedLines(`${item.title} ${item.summary}`, width, bodyFont, 24), 0);
  return headingLines + itemLines;
}

function buildDailyNewsLayoutPlan(width: number, report: ApiDailyNewsReportResponse | null, sections: ApiDailyNewsReportResponse["sections"]): DailyNewsLayoutPlan {
  const pageClass = pickDailyNewsLayoutClass(width, report, sections);
  const headlineClass = pickDailyNewsHeadlineClass(width, report);
  const columnWidth = pageClass === "daily-news-layout-compact" ? width : Math.max(300, (width - 34) / 2);
  const sectionClasses = sections.map((section, index) => {
    const lines = measureDailyNewsSectionLines(section, columnWidth);
    const classes = [index === 0 ? "daily-news-section-feature" : ""];
    if (pageClass !== "daily-news-layout-compact" && (lines >= 31 || section.items.length >= 4)) classes.push("daily-news-section-wide");
    if (lines >= 42) classes.push("daily-news-section-dense");
    return classes.filter(Boolean).join(" ");
  });
  return { pageClass, headlineClass, sectionClasses };
}

type DailyNewsPageProps = {
  shareMode?: boolean;
};

export function DailyNewsSharePage() {
  return <DailyNewsPage shareMode />;
}

export function DailyNewsPage({ shareMode = false }: DailyNewsPageProps) {
  const { apiBaseUrl, loadProviders, providers } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const routeParams = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const shareKey = routeParams.shareKey || "";
  const dateClusterRef = useRef<HTMLDivElement | null>(null);
  const dailyNewsContentRef = useRef<HTMLElement | null>(null);

  const [report, setReport] = useState<ApiDailyNewsReportResponse | null>(null);
  const selectedDate = shareMode ? routeParams.date || report?.report_date || todayDate() : searchParams.get("date") || todayDate();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [backgroundSyncing, setBackgroundSyncing] = useState<string | null>(null);
  const [pendingGeneration, setPendingGeneration] = useState<PendingGeneration | null>(() => readPendingGeneration());
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(selectedDate));
  const [error, setError] = useState<string | null>(null);
  const [dailyNewsLayoutPlan, setDailyNewsLayoutPlan] = useState<DailyNewsLayoutPlan>({
    pageClass: "daily-news-layout-balanced",
    headlineClass: "daily-news-headline-balanced",
    sectionClasses: [],
  });
  const selectedDateRef = useRef(selectedDate);

  useEffect(() => {
    selectedDateRef.current = selectedDate;
  }, [selectedDate]);

  function setDate(nextDate: string) {
    const next = new URLSearchParams(searchParams);
    if (nextDate === todayDate()) {
      next.delete("date");
    } else {
      next.set("date", nextDate);
    }
    setSearchParams(next);
  }

  async function loadReport(date: string, options?: { silent?: boolean }) {
    if (!options?.silent) setLoading(true);
    setError(null);
    try {
      const nextReport = shareMode ? await client.getPublicDailyNews(shareKey, date) : await client.getDailyNews(date);
      setReport(nextReport);
      return nextReport;
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "读取每日新闻失败");
      setReport(null);
      return null;
    } finally {
      if (!options?.silent) setLoading(false);
    }
  }

  async function syncReportInBackground(date: string, cachedReport: ApiDailyNewsReportResponse | null) {
    if (shareMode || date !== todayDate() || backgroundSyncing || pendingGeneration?.date === date) return;
    if (cachedReport?.status === "ready") return;
    if (!hasConfiguredLlmProvider(providers)) {
      const nextProviders = await loadProviders();
      if (!hasConfiguredLlmProvider(nextProviders)) return;
    }
    const syncKey = `${apiBaseUrl}:${date}`;
    let marked = false;
    try {
      if (sessionStorage.getItem(DAILY_NEWS_BACKGROUND_SYNC_KEY) === syncKey) return;
      sessionStorage.setItem(DAILY_NEWS_BACKGROUND_SYNC_KEY, syncKey);
      marked = true;
    } catch {
      // Session storage is a best-effort guard against repeated background generation.
    }
    setBackgroundSyncing(date);
    try {
      const nextReport = await client.generateDailyNews(date, false);
      if (selectedDateRef.current === date) {
        setError(null);
        setReport(nextReport);
      }
    } catch (nextError) {
      if (marked) {
        try {
          sessionStorage.removeItem(DAILY_NEWS_BACKGROUND_SYNC_KEY);
        } catch {
          // Ignore storage cleanup failures.
        }
      }
      if (shouldKeepDailyNewsPendingAfterError(nextError)) {
        window.setTimeout(() => {
          if (selectedDateRef.current === date) void loadReport(date, { silent: true });
        }, 1800);
      }
    } finally {
      setBackgroundSyncing(null);
    }
  }

  async function startGenerateReport(force: boolean) {
    if (!hasConfiguredLlmProvider(providers)) {
      const nextProviders = await loadProviders();
      if (!hasConfiguredLlmProvider(nextProviders)) {
        setError("还没有配置当前使用的大语言模型。请先到设置里的模型服务添加一个 LLM，并设为当前使用。");
        return;
      }
    }
    const pending = { date: selectedDate, startedAt: new Date().toISOString(), force };
    writePendingGeneration(pending);
    setPendingGeneration(pending);
    setGenerating(true);
    setError(null);
    try {
      const nextReport = await client.generateDailyNews(selectedDate, force);
      setReport(nextReport);
      clearPendingGeneration(selectedDate);
      setPendingGeneration(null);
    } catch (nextError) {
      if (shouldKeepDailyNewsPendingAfterError(nextError)) {
        setError("模型生成请求已提交，但连接提前结束；后台可能仍在处理，本页会继续轮询结果。");
        window.setTimeout(() => {
          void loadReport(selectedDate, { silent: true });
        }, 1800);
      } else {
        clearPendingGeneration(selectedDate);
        setPendingGeneration(null);
        setError(nextError instanceof Error ? nextError.message : "生成每日新闻失败");
      }
    } finally {
      setGenerating(false);
    }
  }

  function generateReport(force: boolean) {
    if (shareMode) return;
    if (force && report?.status === "ready") {
      setConfirmRegenerate(true);
      return;
    }
    void startGenerateReport(force);
  }

  function toggleCalendar() {
    if (shareMode) return;
    setCalendarMonth(startOfMonth(selectedDate));
    setCalendarOpen((open) => !open);
  }

  function selectCalendarDate(nextDate: string) {
    if (shareMode) return;
    setDate(nextDate);
    setCalendarOpen(false);
  }

  async function copyShareLink() {
    try {
      const share = await client.createDailyNewsShare(selectedDate);
      const shareUrl = `${publicShareBaseUrl()}/share/daily/${share.share_key}/${share.report_date}`;
      try {
        await navigator.clipboard.writeText(shareUrl);
        window.dispatchEvent(new CustomEvent("oneradar:toast", { detail: { message: "已复制分享链接", tone: "success" } }));
      } catch {
        window.prompt("复制分享链接", shareUrl);
      }
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : "创建分享链接失败";
      setError(message);
    }
  }

  useEffect(() => {
    void loadReport(selectedDate).then((cachedReport) => {
      void syncReportInBackground(selectedDate, cachedReport);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, selectedDate, shareKey, shareMode]);

  useEffect(() => {
    const pending = readPendingGeneration();
    setPendingGeneration(pending);
    setGenerating(Boolean(pending && pending.date === selectedDate));
  }, [selectedDate]);

  useEffect(() => {
    if (shareMode || !pendingGeneration || pendingGeneration.date !== selectedDate) return;
    if (isFreshGeneratedReport(report, pendingGeneration)) {
      clearPendingGeneration(selectedDate);
      setPendingGeneration(null);
      setGenerating(false);
      return;
    }
    const timer = window.setInterval(() => {
      void loadReport(selectedDate, { silent: true });
    }, 3500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGeneration, report, selectedDate, shareMode]);

  useEffect(() => {
    if (shareMode) return;
    if (!providers.length) void loadProviders();
  }, [loadProviders, providers.length, shareMode]);

  useEffect(() => {
    if (!calendarOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (!dateClusterRef.current?.contains(event.target as Node)) setCalendarOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setCalendarOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [calendarOpen]);

  const filteredSections = useMemo(() => {
    if (shareMode) return report?.sections ?? [];
    const keyword = (searchParams.get("q") || "").trim().toLowerCase();
    const sections = report?.sections ?? [];
    if (!keyword) return sections;
    return sections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => [item.title, item.summary, item.entry?.source_title ?? ""].join(" ").toLowerCase().includes(keyword)),
      }))
      .filter((section) => section.items.length > 0 || section.title.toLowerCase().includes(keyword) || section.summary.toLowerCase().includes(keyword));
  }, [report, searchParams, shareMode]);

  const ready = report?.status === "ready";

  useEffect(() => {
    if (!ready) return;
    const element = dailyNewsContentRef.current;
    if (!element) return;

    function updateLayoutPlan() {
      const width = element.getBoundingClientRect().width;
      setDailyNewsLayoutPlan(buildDailyNewsLayoutPlan(width, report, filteredSections));
    }

    updateLayoutPlan();
    const observer = new ResizeObserver(updateLayoutPlan);
    observer.observe(element);
    return () => observer.disconnect();
  }, [filteredSections, ready, report]);

  const isGeneratingSelectedDate = Boolean((generating || pendingGeneration) && pendingGeneration?.date === selectedDate);
  const isBackgroundSyncingSelectedDate = backgroundSyncing === selectedDate && !isGeneratingSelectedDate;
  const isTodayOrFuture = selectedDate >= todayDate();
  const calendarDays = buildCalendarDays(calendarMonth);
  const today = todayDate();
  const isNextMonthDisabled = shiftMonth(calendarMonth, 1) > startOfMonth(today);

  function updateSharePointer(event: PointerEvent<HTMLElement>) {
    if (!shareMode) return;
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty("--daily-news-pointer-x", `${event.clientX - rect.left}px`);
    event.currentTarget.style.setProperty("--daily-news-pointer-y", `${event.clientY - rect.top}px`);
  }

  return (
    <div className={shareMode ? "daily-news-page daily-news-share-page" : "daily-news-page"}>
      {!shareMode && <header className="daily-news-header">
        <button className="btn btn-ghost btn-sm daily-news-corner-nav daily-news-corner-nav-prev" type="button" onClick={() => setDate(shiftDate(selectedDate, -1))}>
          <span className="icon icon-sm">chevron_left</span>
          前一天
        </button>
        <button
          className="btn btn-ghost btn-sm daily-news-corner-nav daily-news-corner-nav-next"
          type="button"
          disabled={isTodayOrFuture}
          onClick={() => setDate(shiftDate(selectedDate, 1))}
        >
          后一天
          <span className="icon icon-sm">chevron_right</span>
        </button>
        <div className="daily-news-date-cluster" ref={dateClusterRef}>
          <button type="button" className="daily-news-date-card" onClick={toggleCalendar} aria-haspopup="dialog" aria-expanded={calendarOpen} title="选择日期">
            <span className="daily-news-date-main">{displayDate(selectedDate)}</span>
            <span className="daily-news-date-year">{displayYear(selectedDate)}</span>
          </button>
          {calendarOpen && (
            <div className="daily-news-calendar-popover" role="dialog" aria-label="选择日报日期">
              <div className="daily-news-calendar-head">
                <button type="button" className="daily-news-calendar-nav" onClick={() => setCalendarMonth((month) => shiftMonth(month, -1))} aria-label="上个月">
                  <span className="icon icon-sm">chevron_left</span>
                </button>
                <strong>{displayCalendarMonth(calendarMonth)}</strong>
                <button
                  type="button"
                  className="daily-news-calendar-nav"
                  disabled={isNextMonthDisabled}
                  onClick={() => setCalendarMonth((month) => shiftMonth(month, 1))}
                  aria-label="下个月"
                >
                  <span className="icon icon-sm">chevron_right</span>
                </button>
              </div>
              <div className="daily-news-calendar-weekdays">
                {["日", "一", "二", "三", "四", "五", "六"].map((weekday) => (
                  <span key={weekday}>{weekday}</span>
                ))}
              </div>
              <div className="daily-news-calendar-grid">
                {calendarDays.map((date) => {
                  const nextDate = dateKey(date);
                  const outsideMonth = !isSameMonth(date, calendarMonth);
                  const isSelected = nextDate === selectedDate;
                  const isToday = nextDate === today;
                  const isFuture = nextDate > today;
                  return (
                    <button
                      type="button"
                      key={nextDate}
                      className={[
                        "daily-news-calendar-day",
                        outsideMonth ? "daily-news-calendar-day-muted" : "",
                        isSelected ? "daily-news-calendar-day-selected" : "",
                        isToday ? "daily-news-calendar-day-today" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={isFuture}
                      onClick={() => selectCalendarDate(nextDate)}
                    >
                      {date.getDate()}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
        <div className="daily-news-title-block">
          <p className="page-eyebrow">Daily Brief</p>
          <h2 className="page-title">每日新闻</h2>
        </div>
      </header>}

      {isGeneratingSelectedDate && (
        <div className="feedback feedback-info daily-news-feedback">
          正在生成 {selectedDate} 的每日新闻。可以切换到其他页面，回来后会继续显示状态并自动读取结果。
        </div>
      )}
      {isBackgroundSyncingSelectedDate && (
        <div className="feedback feedback-info daily-news-feedback">
          正在后台同步今天的日报，当前先显示缓存内容。
        </div>
      )}
      {error && <div className="feedback feedback-error daily-news-feedback">{error}</div>}

      {loading ? (
        <div className="daily-news-empty">
          <span className="icon icon-lg">sync</span>
          <h3>正在读取日报</h3>
        </div>
      ) : !ready ? (
        <div className="daily-news-empty">
          <span className="icon icon-lg">newspaper</span>
          <h3>{shareMode ? "分享日报不可用" : `${selectedDate} 还没有日报`}</h3>
          {shareMode && <p>这个分享链接没有对应的日报，或日报还没有生成。</p>}
          {!shareMode && (
            <button className="btn btn-primary btn-sm" type="button" disabled={isGeneratingSelectedDate} onClick={() => generateReport(false)}>
              <span className="icon icon-sm">{isGeneratingSelectedDate ? "sync" : "auto_awesome"}</span>
              {isGeneratingSelectedDate ? "生成中…" : "生成这一天"}
            </button>
          )}
        </div>
      ) : (
        <main
          ref={dailyNewsContentRef}
          className={`daily-news-content ${shareMode ? "daily-news-share-content" : ""} ${dailyNewsLayoutPlan.pageClass} ${dailyNewsLayoutPlan.headlineClass}`}
          onPointerMove={updateSharePointer}
        >
          <div className="daily-news-meta-line">
            <span>{report?.entry_count ?? 0} 条候选新闻</span>
            <span>生成于 {displayGeneratedAt(report?.generated_at)}</span>
            {report?.provider_name && <span>{report.provider_name}</span>}
          </div>

          <section className="daily-news-lead">
            <p className="daily-news-source-line">
              <span className="daily-news-source-dot" />
              {report?.lead?.entry ? `${report.lead.entry.source_title} · ${displayPublishedAt(report.lead.entry.published_at)}` : "今日重点"}
            </p>
            {report?.lead?.entry ? (
              <a className="daily-news-lead-title" href={report.lead.entry.link} target="_blank" rel="noreferrer">
                {report?.lead?.title || report?.headline || "每日新闻"}
              </a>
            ) : (
              <span className="daily-news-lead-title">
                {report?.lead?.title || report?.headline || "每日新闻"}
              </span>
            )}
            <p>{report?.lead?.summary || report?.headline}</p>
          </section>

          <div className="daily-news-sections-grid">
            {filteredSections.map((section, sectionIndex) => (
              <section className={["daily-news-section", dailyNewsLayoutPlan.sectionClasses[sectionIndex]].filter(Boolean).join(" ")} key={`${section.title}:${sectionIndex}`}>
                <div className="daily-news-section-heading">
                  <span>{String(sectionIndex + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{section.title}</h3>
                    {section.summary && <p>{section.summary}</p>}
                  </div>
                </div>

                <div className="daily-news-entry-list">
                  {section.items.map((item, itemIndex) => (
                    <article className="daily-news-entry" key={itemKey(item, `${sectionIndex}-${itemIndex}`)}>
                      {item.entry ? (
                        <a className="daily-news-entry-title" href={item.entry.link} target="_blank" rel="noreferrer">
                          {item.title}
                        </a>
                      ) : (
                        <span className="daily-news-entry-title">
                          {item.title}
                        </span>
                      )}
                      <p>{item.summary}</p>
                      <div className="daily-news-entry-footer">
                        <span>
                          {item.entry ? `${item.entry.source_title} · ${displayPublishedAt(item.entry.published_at)}` : "模型生成条目"}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
          {!shareMode && (
            <section className="daily-news-regenerate-zone">
              <div className="daily-news-share-actions">
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => void copyShareLink()}>
                  <span className="icon icon-sm">ios_share</span>
                  复制分享链接
                </button>
                <button className="btn btn-secondary btn-sm" type="button" disabled={isGeneratingSelectedDate || loading} onClick={() => generateReport(true)}>
                  <span className="icon icon-sm">{isGeneratingSelectedDate ? "sync" : "auto_awesome"}</span>
                  {isGeneratingSelectedDate ? "重新生成中…" : "重新生成今日日报"}
                </button>
              </div>
            </section>
          )}
        </main>
      )}
      {confirmRegenerate && (
        <ConfirmDialog
          title="重新生成日报"
          body="当前日期的日报会被重新生成并覆盖，只保留最新这一份。确定继续吗？"
          confirmLabel="重新生成"
          busy={isGeneratingSelectedDate}
          onCancel={() => setConfirmRegenerate(false)}
          onConfirm={() => {
            setConfirmRegenerate(false);
            void startGenerateReport(true);
          }}
        />
      )}
    </div>
  );
}
