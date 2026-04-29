import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiItemSummary } from "../api";
import { useAppState } from "../state/appState";

function statusChipClass(status: ApiItemSummary["status"]) {
  switch (status) {
    case "processing": return "chip chip-status-processing";
    case "completed": return "chip chip-status-completed";
    case "failed": return "chip chip-status-failed";
    default: return "chip chip-status-pending";
  }
}

function statusLabel(status: ApiItemSummary["status"]) {
  switch (status) {
    case "processing": return "处理中";
    case "completed": return "已完成";
    case "failed": return "失败";
    default: return "待处理";
  }
}

function formatTime(value?: string) {
  if (!value) return "刚刚";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}


function normalizeProgress(progress?: number) {
  if (typeof progress !== "number" || Number.isNaN(progress)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function sortByRecent(items: ApiItemSummary[]) {
  return [...items].sort((a, b) => {
    const at = Date.parse(a.updated_at ?? a.created_at ?? "");
    const bt = Date.parse(b.updated_at ?? b.created_at ?? "");
    return (Number.isNaN(bt) ? 0 : bt) - (Number.isNaN(at) ? 0 : at);
  });
}

export function LibraryPage() {
  const { folderId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiBaseUrl, folders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const inboxFolderId = workspace?.default_inbox_folder?.id ?? "inbox";

  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const keyword = searchParams.get("q")?.trim() ?? "";
  const tagFilter = searchParams.get("tag")?.trim() ?? "";
  const folderEntries = useMemo(() => folders.filter((f) => f.id !== inboxFolderId), [folders, inboxFolderId]);

  async function refreshLibrary(activeFolderId?: string, kw = "") {
    const r = await client.listItems({
      pageSize: 200,
      folderId: activeFolderId,
      inboxOnly: false,
      keyword: kw || undefined,
      tag: tagFilter || undefined,
    });
    return sortByRecent(r.items.filter((i) => !i.is_inbox && i.folder_id !== inboxFolderId));
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const next = await refreshLibrary(folderId, keyword);
        if (!cancelled) setItems(next);
      } catch {
        if (!cancelled) setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [client, folderId, keyword, tagFilter]);

  const visibleItems = useMemo(() => {
    const kw = keyword.toLowerCase();
    return items.filter((i) =>
      !kw || [i.title, i.summary ?? "", i.folder_name, i.source_url, ...(i.tags ?? [])].join(" ").toLowerCase().includes(kw)
    );
  }, [items, keyword]);

  function updateFilter(key: "tag", value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  }

  const currentFolder = folderEntries.find((f) => f.id === folderId);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
        {/* Top bar */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.18)",
          background: "var(--surface-lowest)", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="icon" style={{ color: folderId ? "var(--tertiary)" : "var(--outline)" }}>
              {folderId ? "folder_open" : "local_library"}
            </span>
            <h2 style={{ fontFamily: "Manrope, sans-serif", fontSize: 16, fontWeight: 700, margin: 0 }}>
              {currentFolder?.name ?? "全部内容"}
            </h2>
            <span style={{ fontSize: 12, color: "var(--outline)" }}>{visibleItems.length} 条</span>
          </div>
          <div className="btn-group" style={{ gap: 8, alignItems: "center" }}>
            <input
              className="input"
              value={tagFilter}
              onChange={(event) => updateFilter("tag", event.target.value)}
              placeholder="标签过滤"
              style={{ width: 120, height: 34, fontSize: 12 }}
            />
          </div>
        </div>

        {/* List */}
        <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
          {loading && (
            <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
              <span className="icon icon-lg" style={{ color: "var(--outline)" }}>sync</span>
            </div>
          )}

          {!loading && visibleItems.length === 0 && (
            <div className="empty-state" style={{ marginTop: 60 }}>
              <div className="empty-state-icon">
                <span className="icon icon-lg">{folderId ? "folder_open" : "local_library"}</span>
              </div>
              <h3>{keyword ? "没有匹配内容" : folderId ? "这个收藏夹还是空的" : "知识库还是空的"}</h3>
            <p>{keyword ? "换个关键词试试。" : "从「稍后阅读」收藏到知识库后，内容会出现在这里。"}</p>
            </div>
          )}

          {visibleItems.map((item) => (
            <LibraryRow key={item.id} item={item} />
          ))}
        </div>
    </div>
  );
}

function LibraryRow({ item }: { item: ApiItemSummary }) {
  const isVideo = item.content_type === "bilibili_video";
  const progress = normalizeProgress(item.progress_percent);
  const showProgress = progress > 0 && progress < 100;


  return (
    <Link
      to={`/items/${item.id}`}
      style={{ display: "block", textDecoration: "none" }}
    >
      <div
        style={{
          display: "flex", alignItems: "flex-start", gap: 0,
          padding: "0 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
          transition: "background 120ms ease",
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--surface-container)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = ""; }}
      >
        {/* Read indicator */}
        <div style={{
          width: 7, height: 7, borderRadius: "50%", marginTop: 20, marginRight: 14, flexShrink: 0,
          background: item.status === "completed" && !item.is_read ? "var(--primary)" : "transparent",
        }} />

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0, padding: "13px 0" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
            <span className="icon icon-sm" style={{ color: isVideo ? "var(--tertiary)" : "var(--on-surface-v)", fontSize: 14 }}>
              {isVideo ? "smart_display" : "article"}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--on-surface-v)" }}>
              {item.folder_name ?? "未分类"}
            </span>
            <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
            <span className={statusChipClass(item.status)} style={{ fontSize: 11 }}>{statusLabel(item.status)}</span>
            {showProgress && (
              <span
                className="chip chip-neutral"
                style={{
                  gap: 6,
                  paddingInline: 8,
                  fontSize: 11,
                  color: "var(--on-surface-v)",
                  borderColor: "rgba(var(--outline-rgb),0.22)",
                  background: "rgba(var(--primary-rgb),0.05)",
                }}
              >
                <span style={{
                  width: 22,
                  height: 4,
                  borderRadius: 999,
                  background: "rgba(var(--outline-rgb),0.16)",
                  overflow: "hidden",
                  flexShrink: 0,
                }}>
                  <span style={{
                    display: "block",
                    width: `${progress}%`,
                    height: "100%",
                    borderRadius: 999,
                    background: "var(--primary)",
                  }} />
                </span>
                {progress}%
              </span>
            )}
          </div>

          <h3 style={{
            fontFamily: "Manrope, sans-serif", fontSize: 14.5, fontWeight: 700,
            color: item.is_read ? "var(--on-surface-v)" : "var(--on-surface)",
            margin: "0 0 4px", lineHeight: 1.35,
          }}>
            {item.title}
          </h3>

          {item.summary && (
            <p style={{
              fontSize: 13, color: "var(--on-surface-v)", margin: 0, lineHeight: 1.6,
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
            }}>
              {item.summary}
            </p>
          )}
        </div>

        {/* Right */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, padding: "13px 0 13px 16px", flexShrink: 0 }}>
          <span style={{ fontSize: 11.5, color: "var(--outline)" }}>
            {formatTime(item.updated_at ?? item.created_at)}
          </span>
          <span className="icon icon-sm" style={{ color: "var(--outline-v)" }}>chevron_right</span>
        </div>
      </div>
    </Link>
  );
}
