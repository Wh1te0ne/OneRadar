import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, createApiClient } from "../api";
import type { ApiDailyNewsEntry, ApiDailyNewsItem, ApiDailyNewsReportResponse } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useAppState } from "../state/appState";
import { hasConfiguredLlmProvider } from "../utils/providers";

const DAILY_NEWS_GENERATION_KEY = "oneradar.daily-news.generation";
const DAILY_NEWS_GENERATION_TTL_MS = 12 * 60 * 1000;

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

function feedArticlePreviewPath(entry: ApiDailyNewsEntry) {
  const params = new URLSearchParams({
    url: entry.link,
    title: entry.title,
    source_title: entry.source_title,
  });
  if (entry.author) params.set("author", entry.author);
  if (entry.published_at) params.set("published_at", entry.published_at);
  if (entry.summary) params.set("summary", entry.summary.slice(0, 600));
  return "/feed/preview?" + params.toString();
}

function sourceFeedPath(entry: ApiDailyNewsEntry) {
  return "/feed?" + new URLSearchParams({ source: entry.source_url }).toString();
}

function itemKey(item: ApiDailyNewsItem, fallback: string) {
  return `${item.entry_id ?? item.entry?.id ?? fallback}:${item.title}`;
}

type PendingGeneration = {
  date: string;
  startedAt: string;
  force: boolean;
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

export function DailyNewsPage() {
  const { apiBaseUrl, loadProviders, providers } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedDate = searchParams.get("date") || todayDate();
  const dateClusterRef = useRef<HTMLDivElement | null>(null);

  const [report, setReport] = useState<ApiDailyNewsReportResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [pendingGeneration, setPendingGeneration] = useState<PendingGeneration | null>(() => readPendingGeneration());
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(selectedDate));
  const [error, setError] = useState<string | null>(null);

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
      setReport(await client.getDailyNews(date));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "读取每日新闻失败");
      setReport(null);
    } finally {
      if (!options?.silent) setLoading(false);
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
      if (nextError instanceof ApiError && nextError.status === 504) {
        setError("模型生成耗时较长，后台仍在处理；回到本页后会继续显示生成状态。");
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
    if (force && report?.status === "ready") {
      setConfirmRegenerate(true);
      return;
    }
    void startGenerateReport(force);
  }

  function toggleCalendar() {
    setCalendarMonth(startOfMonth(selectedDate));
    setCalendarOpen((open) => !open);
  }

  function selectCalendarDate(nextDate: string) {
    setDate(nextDate);
    setCalendarOpen(false);
  }

  useEffect(() => {
    void loadReport(selectedDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, selectedDate]);

  useEffect(() => {
    const pending = readPendingGeneration();
    setPendingGeneration(pending);
    setGenerating(Boolean(pending && pending.date === selectedDate));
  }, [selectedDate]);

  useEffect(() => {
    if (!pendingGeneration || pendingGeneration.date !== selectedDate) return;
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
  }, [pendingGeneration, report, selectedDate]);

  useEffect(() => {
    if (!providers.length) void loadProviders();
  }, [loadProviders, providers.length]);

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
    const keyword = (searchParams.get("q") || "").trim().toLowerCase();
    const sections = report?.sections ?? [];
    if (!keyword) return sections;
    return sections
      .map((section) => ({
        ...section,
        items: section.items.filter((item) => [item.title, item.summary, item.entry?.source_title ?? ""].join(" ").toLowerCase().includes(keyword)),
      }))
      .filter((section) => section.items.length > 0 || section.title.toLowerCase().includes(keyword) || section.summary.toLowerCase().includes(keyword));
  }, [report, searchParams]);

  const ready = report?.status === "ready";
  const isGeneratingSelectedDate = Boolean((generating || pendingGeneration) && pendingGeneration?.date === selectedDate);
  const isTodayOrFuture = selectedDate >= todayDate();
  const calendarDays = buildCalendarDays(calendarMonth);
  const today = todayDate();
  const isNextMonthDisabled = shiftMonth(calendarMonth, 1) > startOfMonth(today);

  return (
    <div className="daily-news-page">
      <header className="daily-news-header">
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
      </header>

      {isGeneratingSelectedDate && (
        <div className="feedback feedback-info daily-news-feedback">
          正在生成 {selectedDate} 的每日新闻。可以切换到其他页面，回来后会继续显示状态并自动读取结果。
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
          <h3>{selectedDate} 还没有日报</h3>
          <p>点击生成后，会调用已配置的大语言模型，将当天订阅源新闻翻译、筛选并总结成一份固定结构日报。</p>
          <button className="btn btn-primary btn-sm" type="button" disabled={isGeneratingSelectedDate} onClick={() => generateReport(false)}>
            <span className="icon icon-sm">{isGeneratingSelectedDate ? "sync" : "auto_awesome"}</span>
            {isGeneratingSelectedDate ? "生成中…" : "生成这一天"}
          </button>
        </div>
      ) : (
        <main className="daily-news-content">
          <div className="daily-news-meta-line">
            <span>{report?.entry_count ?? 0} 条候选新闻</span>
            <span>生成于 {displayGeneratedAt(report?.generated_at)}</span>
            {report?.model_name && <span>{report.provider_name ?? "模型"} · {report.model_name}</span>}
          </div>

          <section className="daily-news-lead">
            <p className="daily-news-source-line">
              <span className="daily-news-source-dot" />
              {report?.lead?.entry ? `${report.lead.entry.source_title} · ${displayPublishedAt(report.lead.entry.published_at)}` : "今日重点"}
            </p>
            <button
              type="button"
              className="daily-news-lead-title"
              onClick={() => report?.lead?.entry && navigate(feedArticlePreviewPath(report.lead.entry))}
              disabled={!report?.lead?.entry}
            >
              {report?.lead?.title || report?.headline || "每日新闻"}
            </button>
            <p>{report?.lead?.summary || report?.headline}</p>
            {report?.lead?.entry && (
              <Link to={sourceFeedPath(report.lead.entry)} className="daily-news-source-link">
                查看订阅源
                <span className="icon icon-sm">chevron_right</span>
              </Link>
            )}
          </section>

          {filteredSections.map((section, sectionIndex) => (
            <section className="daily-news-section" key={`${section.title}:${sectionIndex}`}>
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
                    <button
                      type="button"
                      className="daily-news-entry-title"
                      onClick={() => item.entry && navigate(feedArticlePreviewPath(item.entry))}
                      disabled={!item.entry}
                    >
                      {item.title}
                    </button>
                    <p>{item.summary}</p>
                    <div className="daily-news-entry-footer">
                      <span>
                        {item.entry ? `${item.entry.source_title} · ${displayPublishedAt(item.entry.published_at)}` : "模型生成条目"}
                      </span>
                      {item.entry && (
                        <Link to={sourceFeedPath(item.entry)}>
                          查看订阅源
                          <span className="icon icon-sm">chevron_right</span>
                        </Link>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
          <section className="daily-news-regenerate-zone">
            <button className="btn btn-secondary btn-sm" type="button" disabled={isGeneratingSelectedDate || loading} onClick={() => generateReport(true)}>
              <span className="icon icon-sm">{isGeneratingSelectedDate ? "sync" : "auto_awesome"}</span>
              {isGeneratingSelectedDate ? "重新生成中…" : "重新生成今日日报"}
            </button>
            <p>会按当前订阅源的最新缓存重新调用大语言模型，并覆盖这一天已有的日报。</p>
          </section>
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
