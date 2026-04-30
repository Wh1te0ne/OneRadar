import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiFeedArticlePreviewResponse } from "../api/types";
import { useAppState } from "../state/appState";

const FEED_ARTICLE_PREVIEW_CACHE_KEY = "oneradar.feed.articlePreviewCache.v1";
const FEED_ARTICLE_PREVIEW_CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const FEED_ARTICLE_PREVIEW_CACHE_LIMIT = 40;

type CachedFeedArticlePreview = {
  cachedAt: number;
  preview: ApiFeedArticlePreviewResponse;
};

function formatDisplayDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function splitParagraphs(value: string) {
  return value
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function hostLabel(value?: string | null) {
  if (!value) return "RSS";
  try {
    return new URL(value).host;
  } catch {
    return value;
  }
}

function wordCount(text: string) {
  const compact = text.replace(/\s+/g, "");
  return compact.length;
}

function loadPreviewCache(): Record<string, CachedFeedArticlePreview> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(FEED_ARTICLE_PREVIEW_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, CachedFeedArticlePreview> : {};
  } catch {
    return {};
  }
}

function getCachedPreview(url: string): ApiFeedArticlePreviewResponse | null {
  const cached = loadPreviewCache()[url];
  if (!cached || Date.now() - cached.cachedAt > FEED_ARTICLE_PREVIEW_CACHE_TTL_MS) {
    return null;
  }
  return cached.preview;
}

function removeCachedPreview(url: string) {
  if (typeof window === "undefined") return;
  const cache = loadPreviewCache();
  delete cache[url];
  try {
    window.localStorage.setItem(FEED_ARTICLE_PREVIEW_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Preview cache is best-effort only.
  }
}

function saveCachedPreview(url: string, preview: ApiFeedArticlePreviewResponse) {
  if (typeof window === "undefined") return;
  const cache = loadPreviewCache();
  cache[url] = { cachedAt: Date.now(), preview };
  const entries = Object.entries(cache)
    .sort((a, b) => b[1].cachedAt - a[1].cachedAt)
    .slice(0, FEED_ARTICLE_PREVIEW_CACHE_LIMIT);
  try {
    window.localStorage.setItem(FEED_ARTICLE_PREVIEW_CACHE_KEY, JSON.stringify(Object.fromEntries(entries)));
  } catch {
    // Preview cache is best-effort only.
  }
}

export function FeedArticlePreviewPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { apiBaseUrl, loadFolders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [preview, setPreview] = useState<ApiFeedArticlePreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const sourceUrl = searchParams.get("url") ?? "";
  const fallbackTitle = searchParams.get("title");
  const fallbackSourceTitle = searchParams.get("source_title");
  const fallbackAuthor = searchParams.get("author");
  const fallbackPublishedAt = searchParams.get("published_at");
  const fallbackSummary = searchParams.get("summary");
  const savedFromList = searchParams.get("is_saved") === "1";
  const savedItemIdFromList = searchParams.get("saved_item_id");
  const savedUidFromList = searchParams.get("saved_uid");

  function withKnownSavedState(next: ApiFeedArticlePreviewResponse): ApiFeedArticlePreviewResponse {
    if (!savedFromList || next.is_saved) return next;
    return {
      ...next,
      is_saved: true,
      saved_item_id: savedItemIdFromList,
      saved_uid: savedUidFromList,
      can_generate_ai: true,
    };
  }

  useEffect(() => {
    let cancelled = false;
    if (!sourceUrl.trim()) {
      setError("缺少文章链接。");
      setLoading(false);
      return;
    }

    const cached = getCachedPreview(sourceUrl);
    if (cached) {
      setPreview(withKnownSavedState(cached));
      setLoading(false);
      setError(null);
      setSaveMessage(null);
      return;
    }

    setLoading(true);
    setError(null);
    setSaveMessage(null);
    client
      .getFeedArticlePreview({
        url: sourceUrl,
        title: fallbackTitle,
        sourceTitle: fallbackSourceTitle,
        author: fallbackAuthor,
        publishedAt: fallbackPublishedAt,
        summary: fallbackSummary,
      })
      .then((next) => {
        if (!cancelled) {
          const nextPreview = withKnownSavedState(next);
          setPreview(nextPreview);
          saveCachedPreview(sourceUrl, nextPreview);
        }
      })
      .catch((nextError) => {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "文章预览失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [client, fallbackAuthor, fallbackPublishedAt, fallbackSourceTitle, fallbackSummary, fallbackTitle, refreshNonce, savedFromList, savedItemIdFromList, savedUidFromList, sourceUrl]);

  function handleRefetch() {
    if (!sourceUrl) return;
    removeCachedPreview(sourceUrl);
    setPreview(null);
    setSaveMessage(null);
    setRefreshNonce((current) => current + 1);
  }

  async function handleSave() {
    const targetUrl = preview?.source_url || sourceUrl;
    if (!targetUrl) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const result = await client.importItem(targetUrl, "article", {
        title: preview?.title,
        siteTitle: preview?.site_title,
        author: preview?.author,
        publishedAt: preview?.published_at,
        summary: preview?.summary,
        parsedText: preview?.plain_text,
        parserName: preview?.parser_name,
        parserVersion: preview?.parser_version,
        generateSummary: true,
      });
      await loadFolders();
      setSaveMessage(result.is_duplicate ? `已存在：${result.uid}` : `已加入稍后阅读：${result.uid}`);
      navigate(`/items/${result.item_id}?from=feed`);
    } catch (nextError) {
      setSaveMessage(nextError instanceof Error ? nextError.message : "加入稍后阅读失败");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="reader-page reader-page-feedback">
        <div style={{ textAlign: "center" }}>
          <span className="icon icon-lg" style={{ color: "var(--primary)", display: "block", marginBottom: 12, animation: "spin 1s linear infinite" }}>sync</span>
          <p className="text-meta">正在加载阅读预览…</p>
        </div>
      </div>
    );
  }

  if (error || !preview) {
    return (
      <div className="reader-page reader-page-feedback">
        <div className="card" style={{ width: "min(560px, 100%)", padding: 22 }}>
          <div className="feedback feedback-error" style={{ marginBottom: 14 }}>{error ?? "未找到文章预览。"}</div>
          <div className="btn-group">
            <Link className="btn btn-ghost btn-sm" to="/feed">
              <span className="icon icon-sm">arrow_back</span>
              返回订阅源
            </Link>
            {sourceUrl && (
              <a className="btn btn-secondary btn-sm" href={sourceUrl} target="_blank" rel="noreferrer">
                <span className="icon icon-sm">open_in_new</span>
                打开原文
              </a>
            )}
          </div>
        </div>
      </div>
    );
  }

  const paragraphs = splitParagraphs(preview.plain_text);
  const displayDate = formatDisplayDate(preview.published_at);
  const origin = preview.final_url || preview.source_url;

  return (
    <div className="reader-page">
      <div className="reader-shell">
        <div className="reader-toolbar">
          <div className="reader-toolbar-meta">
            <Link className="btn btn-ghost btn-sm" to="/feed">
              <span className="icon icon-sm">arrow_back</span>
              返回
            </Link>
            <span className="chip chip-neutral">RSS 预览</span>
            <span className="reader-toolbar-source">{preview.site_title || hostLabel(origin)}</span>
          </div>
          <div className="btn-group reader-toolbar-actions">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void handleSave()} disabled={saving || preview.is_saved}>
              <span className="icon icon-sm">{preview.is_saved ? "bookmark_added" : saving ? "sync" : "bookmark_add"}</span>
              {preview.is_saved ? "已保存" : saving ? "加入中…" : "加入稍后阅读"}
            </button>
            {preview.is_saved && preview.saved_item_id && (
              <Link className="btn btn-secondary btn-sm" to={`/items/${preview.saved_item_id}?from=feed`}>
                <span className="icon icon-sm">menu_book</span>
                阅读页
              </Link>
            )}
            <button type="button" className="btn btn-secondary btn-sm" onClick={handleRefetch} disabled={loading}>
              <span className="icon icon-sm">sync</span>
              重新获取
            </button>
            <a className="btn btn-secondary btn-sm" href={origin} target="_blank" rel="noreferrer">
              <span className="icon icon-sm">open_in_new</span>
              原文
            </a>
          </div>
        </div>

        <div className="reader-layout">
          <article className="reader-column">
            {saveMessage && <div className="feedback feedback-info" style={{ marginBottom: 20 }}>{saveMessage}</div>}
            <h1 className="article-title">{preview.title}</h1>
            <div className="article-meta-row">
              {preview.site_title && <span className="chip chip-neutral">{preview.site_title}</span>}
              {preview.author && <span className="text-caption">{preview.author}</span>}
              {displayDate && <span className="text-caption">{displayDate}</span>}
              {preview.is_saved && <span className="chip chip-secondary">已加入稍后阅读</span>}
            </div>

            <div className="feed-preview-body-section">
              <div className="article-section-title">正文</div>
              <div className="prose">
                {paragraphs.length ? paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>) : <p>该订阅项暂时没有可阅读正文。</p>}
              </div>
            </div>
          </article>

          <aside className="card detail-rail reader-rail" style={{ padding: 0, overflow: "hidden" }}>
            <div style={{ padding: 20 }}>
              <div className="reader-context-panel">
                <div className="reader-context-kicker">来源</div>
                <div className="reader-context-origin">{preview.site_title || hostLabel(origin)}</div>
                <div className="reader-context-stats">
                  <div>
                    <span>{paragraphs.length}</span>
                    <small>段落</small>
                  </div>
                  <div>
                    <span>{wordCount(preview.plain_text)}</span>
                    <small>字数</small>
                  </div>
                </div>
              </div>

              {preview.summary && (
                <div className="reader-context-panel">
                  <div className="reader-context-kicker">RSS 摘要</div>
                  <p className="text-meta" style={{ margin: 0, lineHeight: 1.65 }}>{preview.summary}</p>
                </div>
              )}

              <div className="reader-context-panel">
                <div className="reader-context-kicker">AI</div>
                <p className="text-meta" style={{ margin: 0, lineHeight: 1.65 }}>
                  {preview.is_saved
                    ? "这篇文章已保存。阅读页会显示 AI 生成中、失败原因和重新生成入口。"
                    : "当前只是预览，不会自动生成 AI 摘要。加入稍后阅读后会进入 AI 摘要生成流程。"}
                </p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
