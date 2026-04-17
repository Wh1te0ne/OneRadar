import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
    case "completed": return "可阅读";
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

function sortByRecent(items: ApiItemSummary[]) {
  return [...items].sort((a, b) => {
    const at = Date.parse(a.updated_at ?? a.created_at ?? "");
    const bt = Date.parse(b.updated_at ?? b.created_at ?? "");
    return (Number.isNaN(bt) ? 0 : bt) - (Number.isNaN(at) ? 0 : at);
  });
}

function fallbackSummary(item: ApiItemSummary) {
  if (item.summary?.trim()) return item.summary.trim();
  return item.content_type === "bilibili_video" ? "视频条目，等待处理。" : "文章条目，等待处理。";
}

type SortMode = "recent" | "unread" | "type";

export function InboxPage() {
  const [searchParams] = useSearchParams();
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("recent");
  const [movingId, setMovingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ id: string; msg: string } | null>(null);

  const customFolders = useMemo(() => folders.filter((f) => !f.is_builtin), [folders]);
  const keyword = searchParams.get("q")?.trim() ?? "";

  async function refreshInbox(kw: string) {
    const r = await client.listItems({ inboxOnly: true, pageSize: 100, keyword: kw || undefined });
    return sortByRecent(r.items);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true); setLoadError(null);
      try {
        const next = await refreshInbox(keyword);
        if (!cancelled) setItems(next);
      } catch {
        if (!cancelled) { setItems([]); setLoadError("无法加载稍后阅读"); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [client, keyword]);

  const visibleItems = useMemo(() => {
    const kw = keyword.toLowerCase();
    let result = items.filter((item) =>
      !kw || [item.title, item.summary ?? "", item.source_url, item.uid].join(" ").toLowerCase().includes(kw)
    );
    if (sortMode === "unread") result = result.filter((i) => !i.is_read);
    if (sortMode === "type") result = [...result].sort((a, b) => a.content_type.localeCompare(b.content_type));
    return result;
  }, [items, keyword, sortMode]);

  async function handleMoveToLibrary(itemId: string, folderId: string) {
    setMovingId(itemId);
    try {
      const result = await client.moveItem(itemId, folderId);
      setFeedback({ id: itemId, msg: `已移入 ${result.folder_name}` });
      setItems(await refreshInbox(keyword));
      await loadFolders();
      setTimeout(() => setFeedback(null), 2000);
    } catch {
      // silent
    } finally {
      setMovingId(null);
    }
  }

  const unreadCount = items.filter((i) => i.status === "completed" && !i.is_read).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Top bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid rgba(172,179,183,0.18)",
        background: "var(--surface-lowest)", flexShrink: 0, gap: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ fontFamily: "Manrope, sans-serif", fontSize: 16, fontWeight: 700, margin: 0 }}>
            稍后阅读
          </h2>
          {unreadCount > 0 && (
            <span className="chip chip-primary">{unreadCount} 未读</span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* Sort */}
          <div style={{ display: "flex", gap: 2, background: "var(--surface-container)", padding: 4, borderRadius: "var(--radius-sm)" }}>
            {([ ["recent", "最新"], ["unread", "未读"], ["type", "类型"] ] as [SortMode, string][]).map(([val, label]) => (
              <button
                key={val}
                type="button"
                onClick={() => setSortMode(val)}
                style={{
                  padding: "4px 12px", borderRadius: "calc(var(--radius-sm) - 2px)",
                  border: "none", cursor: "pointer", fontSize: 12.5, fontWeight: sortMode === val ? 600 : 500,
                  background: sortMode === val ? "var(--surface-lowest)" : "transparent",
                  color: sortMode === val ? "var(--primary)" : "var(--on-surface-v)",
                  boxShadow: sortMode === val ? "var(--shadow-card)" : "none",
                  transition: "all 140ms ease",
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 12, color: "var(--outline)" }}>{visibleItems.length} 条</span>
        </div>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {loadError && (
          <div className="feedback feedback-error" style={{ margin: "16px 28px" }}>{loadError}</div>
        )}

        {!loading && visibleItems.length === 0 && (
          <div className="empty-state" style={{ marginTop: 80 }}>
            <div className="empty-state-icon">
              <span className="icon icon-lg">bookmarks</span>
            </div>
            <h3>{keyword ? "没有匹配内容" : "稍后阅读为空"}</h3>
            <p>{keyword ? "换个关键词试试。" : "通过「导入」页添加的内容会先出现在这里。"}</p>
            {!keyword && (
              <Link className="btn btn-primary btn-sm" to="/import" style={{ marginTop: 16 }}>
                <span className="icon icon-sm">add_link</span>
                去导入内容
              </Link>
            )}
          </div>
        )}

        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <span className="icon icon-lg" style={{ color: "var(--outline)", animation: "none" }}>sync</span>
          </div>
        )}

        {visibleItems.map((item) => (
          <InboxRow
            key={item.id}
            item={item}
            folders={customFolders}
            isMoving={movingId === item.id}
            feedbackMsg={feedback?.id === item.id ? feedback.msg : null}
            onMoveToFolder={(folderId) => void handleMoveToLibrary(item.id, folderId)}
          />
        ))}
      </div>
    </div>
  );
}

function InboxRow({
  item,
  folders,
  isMoving,
  feedbackMsg,
  onMoveToFolder,
}: {
  item: ApiItemSummary;
  folders: { id: string; name: string }[];
  isMoving: boolean;
  feedbackMsg: string | null;
  onMoveToFolder: (folderId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState(folders[0]?.id ?? "");

  const isVideo = item.content_type === "bilibili_video";

  return (
    <div
      style={{
        borderBottom: "1px solid rgba(172,179,183,0.12)",
        transition: "background 120ms ease",
        background: expanded ? "var(--surface-container)" : undefined,
      }}
    >
      {/* Main row */}
      <div
        style={{ display: "flex", alignItems: "flex-start", gap: 0, padding: "0 28px", cursor: "pointer" }}
        onClick={() => setExpanded(!expanded)}
        onMouseEnter={(e) => { if (!expanded) (e.currentTarget as HTMLDivElement).style.background = "var(--surface-low)"; }}
        onMouseLeave={(e) => { if (!expanded) (e.currentTarget as HTMLDivElement).style.background = ""; }}
      >
        {/* Unread dot */}
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
              {item.source_url ? new URL(item.source_url.startsWith("http") ? item.source_url : `https://${item.source_url}`).hostname.replace("www.", "") : "未知来源"}
            </span>
            <span style={{ fontSize: 11, color: "var(--outline-v)" }}>·</span>
            <span className={statusChipClass(item.status)} style={{ fontSize: 11 }}>{statusLabel(item.status)}</span>
          </div>

          <h3 style={{
            fontFamily: "Manrope, sans-serif", fontSize: 14.5, fontWeight: 700,
            color: item.is_read ? "var(--on-surface-v)" : "var(--on-surface)",
            margin: "0 0 4px", lineHeight: 1.35,
          }}>
            {item.title}
          </h3>

          <p style={{
            fontSize: 13, color: "var(--on-surface-v)", margin: 0, lineHeight: 1.6,
            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
          }}>
            {fallbackSummary(item)}
          </p>
        </div>

        {/* Right */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, padding: "13px 0 13px 16px", flexShrink: 0 }}>
          <span style={{ fontSize: 11.5, color: "var(--outline)" }}>
            {new Date(item.updated_at ?? item.created_at ?? "").toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
          </span>
          <span className="icon icon-sm" style={{ color: expanded ? "var(--primary)" : "var(--outline)" }}>
            {expanded ? "keyboard_arrow_up" : "keyboard_arrow_down"}
          </span>
        </div>
      </div>

      {/* Expanded actions */}
      {expanded && (
        <div style={{ padding: "0 28px 14px 50px", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Link
            className="btn btn-primary btn-sm"
            to={`/items/${item.id}`}
            onClick={(e) => e.stopPropagation()}
          >
            <span className="icon icon-sm">auto_stories</span>
            打开阅读
          </Link>

          {folders.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <select
                className="select"
                style={{ padding: "6px 10px", fontSize: 12.5, width: "auto", minWidth: 120 }}
                value={selectedFolder}
                onChange={(e) => setSelectedFolder(e.target.value)}
                onClick={(e) => e.stopPropagation()}
              >
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
              <button
                className="btn btn-secondary btn-sm"
                type="button"
                disabled={isMoving || !selectedFolder}
                onClick={(e) => { e.stopPropagation(); onMoveToFolder(selectedFolder); }}
              >
                <span className="icon icon-sm">drive_file_move</span>
                {isMoving ? "移动中…" : "存入知识库"}
              </button>
            </div>
          )}

          {folders.length === 0 && (
            <Link className="btn btn-ghost btn-sm" to="/library" onClick={(e) => e.stopPropagation()}>
              <span className="icon icon-sm">create_new_folder</span>
              先去知识库建文件夹
            </Link>
          )}

          {feedbackMsg && (
            <span style={{ fontSize: 12, color: "var(--success)", fontWeight: 600 }}>✓ {feedbackMsg}</span>
          )}
        </div>
      )}
    </div>
  );
}
