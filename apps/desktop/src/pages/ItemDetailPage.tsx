import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiItemDetail } from "../api";
import { useAppState } from "../state/appState";

function statusLabel(status?: ApiItemDetail["status"]) {
  switch (status) {
    case "processing": return "处理中";
    case "completed": return "已完成";
    case "failed": return "失败";
    default: return "待处理";
  }
}

function statusChipClass(status?: ApiItemDetail["status"]) {
  switch (status) {
    case "processing": return "chip chip-status-processing";
    case "completed": return "chip chip-status-completed";
    case "failed": return "chip chip-status-failed";
    default: return "chip chip-status-pending";
  }
}

function summaryTypeLabel(t: string) {
  switch (t) {
    case "one_line": return "一句话摘要";
    case "short": return "短摘要";
    case "outline": return "结构大纲";
    case "key_points": return "关键要点";
    default: return "摘要";
  }
}

function formatTranscriptTime(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function splitParagraphs(value?: string | null) {
  return value ? value.split(/\n+/).filter(Boolean) : [];
}

export function ItemDetailPage() {
  const { itemId = "" } = useParams();
  const location = useLocation();
  const { apiBaseUrl, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [item, setItem] = useState<ApiItemDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!itemId) { setItem(null); return; }
      setLoading(true); setError(null);
      try {
        const r = await client.getItem(itemId);
        if (!cancelled) setItem(r);
      } catch (e) {
        if (!cancelled) { setItem(null); setError(e instanceof Error ? e.message : "读取条目失败"); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [client, itemId]);

  const from = new URLSearchParams(location.search).get("from");
  const paragraphs = splitParagraphs(item?.parsed_document?.plain_text);
  const isVideo = item?.content_type === "bilibili_video";
  const hasTranscript = (item?.transcript?.segments?.length ?? 0) > 0 || Boolean(item?.transcript?.full_text?.trim());
  const hasArticleBody = paragraphs.length > 0;
  const uid = item?.uid ?? item?.id ?? itemId;
  const folderName = item?.folder_name ?? workspace?.default_inbox_folder?.name ?? "收件箱";
  const sourceLabel = item?.metadata.site_name ?? item?.source_url ?? "未知来源";
  const transcriptSegments = item?.transcript?.segments ?? [];
  const progress = item?.reading_state?.progress_percent ?? 0;

  const backHref = (() => {
    if (from === "feed") return "/feed";
    if (from === "inbox") return "/inbox";
    if (item?.folder_id && item.folder_id !== "inbox") return `/folders/${item.folder_id}`;
    if (item?.is_inbox) return "/inbox";
    return "/library";
  })();

  if (loading) {
    return (
      <div className="page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 400 }}>
        <div style={{ textAlign: "center" }}>
          <span className="icon icon-lg" style={{ color: "var(--primary)", display: "block", marginBottom: 12, animation: "spin 1s linear infinite" }}>sync</span>
          <p className="text-meta">正在加载…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="feedback feedback-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="page-eyebrow">阅读</p>
          <h2 className="page-title" style={{ fontSize: "1.6rem" }}>
            {item?.title ?? "正在读取条目"}
          </h2>
          <p className="page-lead">{folderName} · {sourceLabel}</p>
        </div>
        <div className="btn-group" style={{ flexShrink: 0, paddingTop: 8 }}>
          <Link className="btn btn-ghost btn-sm" to={backHref}>
            <span className="icon icon-sm">arrow_back</span>
            返回
          </Link>
          {item?.source_url && (
            <a className="btn btn-secondary btn-sm" href={item.source_url} target="_blank" rel="noreferrer">
              <span className="icon icon-sm">open_in_new</span>
              原文
            </a>
          )}
        </div>
      </div>

      {/* Reader layout */}
      <div className="reader-layout">
        {/* Main reading column */}
        <div className="reader-column">
          {/* Reading progress bar */}
          {progress > 0 && (
            <div className="reading-progress-bar">
              <div className="reading-progress-fill" style={{ width: `${progress}%` }} />
            </div>
          )}

          {/* Article title + meta */}
          <h1 className="article-title">{item?.title ?? "—"}</h1>
          <div className="article-meta-row">
            <span className={statusChipClass(item?.status)}>{statusLabel(item?.status)}</span>
            <span className="chip chip-neutral">
              <span className="icon icon-sm">{isVideo ? "smart_display" : "article"}</span>
              {isVideo ? "视频" : "文章"}
            </span>
            <span className="chip chip-neutral">UID {uid}</span>
            {item?.metadata.author_name && (
              <span className="text-caption">{item.metadata.author_name}</span>
            )}
            {item?.metadata.published_at && (
              <span className="text-caption">{item.metadata.published_at}</span>
            )}
          </div>

          {/* Video transcript */}
          {isVideo && (
            <div className="article-section">
              <div className="article-section-title">转写正文</div>
              {transcriptSegments.length ? (
                <div className="transcript-list">
                  {transcriptSegments.map((seg, idx) => (
                    <div className="transcript-row" key={`${String(seg.start_ms)}-${String(idx)}`}>
                      <div className="transcript-time">{formatTranscriptTime(seg.start_ms)}</div>
                      <div>
                        <p className="transcript-speaker">{seg.speaker ?? "说话人"}</p>
                        <p className="transcript-text">{seg.text}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : item?.transcript?.full_text ? (
                <p className="prose">{item.transcript.full_text}</p>
              ) : (
                <p className="text-meta">暂未生成转写。</p>
              )}
            </div>
          )}

          {/* Article body */}
          {!isVideo && (
            <div className="article-section">
              <div className="article-section-title">正文</div>
              <div className="prose">
                {hasArticleBody
                  ? paragraphs.map((p) => <p key={p}>{p}</p>)
                  : <p className="text-meta">暂未生成可读正文。</p>
                }
              </div>
            </div>
          )}

          {/* Video article body */}
          {isVideo && hasArticleBody && (
            <div className="article-section">
              <div className="article-section-title">整理稿</div>
              <div className="prose">
                {paragraphs.map((p) => <p key={p}>{p}</p>)}
              </div>
            </div>
          )}

          {/* Article transcript reference */}
          {!isVideo && hasTranscript && (
            <div className="article-section">
              <div className="article-section-title">转写参考</div>
              {transcriptSegments.length ? (
                <div className="transcript-list">
                  {transcriptSegments.map((seg, idx) => (
                    <div className="transcript-row" key={`${String(seg.start_ms)}-${String(idx)}`}>
                      <div className="transcript-time">{formatTranscriptTime(seg.start_ms)}</div>
                      <div>
                        <p className="transcript-speaker">{seg.speaker ?? "说话人"}</p>
                        <p className="transcript-text">{seg.text}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-meta">{item?.transcript?.full_text ?? "暂无转写参考。"}</p>
              )}
            </div>
          )}

          {/* Summaries */}
          <div className="article-section">
            <div className="article-section-title">AI 摘要</div>
            {item?.summaries?.length ? (
              <ul className="summary-list">
                {item.summaries.map((s) => (
                  <li key={`${s.summary_type}-${String(s.version ?? 0)}`} className="summary-item">
                    <div style={{ fontSize: 11, fontWeight: 700, color: "var(--primary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                      {summaryTypeLabel(s.summary_type)}
                    </div>
                    <div>{s.content}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-meta">暂无摘要。</p>
            )}
          </div>

          {/* Highlights & Notes */}
          {((item?.highlights?.length ?? 0) > 0 || (item?.notes?.length ?? 0) > 0) && (
            <div className="article-section">
              <div className="article-section-title">标注与笔记</div>
              {item?.highlights?.length ? (
                <ul className="summary-list">
                  {item.highlights.map((h, idx) => (
                    <li key={h.id ?? String(idx)} className="summary-item" style={{ borderLeftColor: "var(--tertiary-container)" }}>
                      <span className="icon icon-sm" style={{ color: "var(--tertiary)", marginRight: 6 }}>format_quote</span>
                      {h.quote_text ?? h.text ?? ""}
                    </li>
                  ))}
                </ul>
              ) : null}
              {item?.notes?.length ? (
                <ul className="summary-list" style={{ marginTop: 12 }}>
                  {item.notes.map((n, idx) => (
                    <li key={n.id ?? String(idx)} className="summary-item">
                      <span className="icon icon-sm" style={{ color: "var(--secondary)", marginRight: 6 }}>sticky_note_2</span>
                      {n.content ?? n.text ?? ""}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </div>

        {/* Right rail */}
        <div className="card detail-rail" style={{ padding: 0, overflow: "hidden" }}>
          <div className="card-header" style={{ padding: "16px 20px", borderBottom: "1px solid rgba(172,179,183,0.15)" }}>
            <span className="card-title">条目信息</span>
            <span className="card-meta">{loading ? "加载中…" : item ? "已同步" : "—"}</span>
          </div>

          <div style={{ padding: "16px 20px" }}>
            <div className="info-list">
              {[
                { label: "UID", value: uid },
                { label: "位置", value: folderName },
                { label: "来源", value: sourceLabel },
                { label: "发布时间", value: item?.metadata.published_at ?? "未知" },
                { label: "作者", value: item?.metadata.author_name ?? "未署名" },
              ].map((row) => (
                <div key={row.label} className="info-row">
                  <span className="info-row-label">{row.label}</span>
                  <span className="info-row-value">{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Reading state */}
          <div style={{ padding: "0 20px 16px", borderTop: "1px solid rgba(172,179,183,0.12)" }}>
            <div className="rail-section-title" style={{ marginTop: 16 }}>阅读状态</div>
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span className="text-caption">进度</span>
                <span className="text-caption">{progress}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
              </div>
            </div>
            <div className="info-list">
              <div className="info-row">
                <span className="info-row-label">上次阅读</span>
                <span className="info-row-value" style={{ fontSize: 12 }}>{item?.reading_state?.last_read_at ?? "暂无"}</span>
              </div>
              <div className="info-row">
                <span className="info-row-label">收藏</span>
                <span className="info-row-value">
                  <span className="icon icon-sm" style={{ color: item?.reading_state?.is_favorited ? "var(--warning)" : "var(--outline-v)" }}>
                    {item?.reading_state?.is_favorited ? "star" : "star_border"}
                  </span>
                </span>
              </div>
            </div>
          </div>

          {/* Tags */}
          {(item?.tags?.length ?? 0) > 0 && (
            <div style={{ padding: "0 20px 16px", borderTop: "1px solid rgba(172,179,183,0.12)" }}>
              <div className="rail-section-title" style={{ marginTop: 16 }}>标签</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {item?.tags?.map((tag, idx) => (
                  <span key={idx} className="chip chip-secondary">
                    {typeof tag === "string" ? tag : tag.name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Collections */}
          {(item?.collections?.length ?? 0) > 0 && (
            <div style={{ padding: "0 20px 16px", borderTop: "1px solid rgba(172,179,183,0.12)" }}>
              <div className="rail-section-title" style={{ marginTop: 16 }}>收藏夹</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {item?.collections?.map((c, idx) => (
                  <span key={idx} className="chip chip-primary">
                    {String(c.name ?? c.id)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
