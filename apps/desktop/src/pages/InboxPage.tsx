import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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


function normalizeProgress(progress?: number) {
  if (typeof progress !== "number" || Number.isNaN(progress)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(progress)));
}

type SortMode = "recent" | "unread" | "type";
type ItemContextMenuState = {
  itemId: string;
  x: number;
  y: number;
  submenuPlacement: "left" | "right";
  submenuMaxHeight: number;
};

function createContextMenuState(itemId: string, x: number, y: number): ItemContextMenuState {
  const margin = 12;
  const menuWidth = 220;
  const submenuWidth = 220;
  const menuHeight = 172;
  const clampedX = Math.max(margin, Math.min(x, window.innerWidth - menuWidth - margin));
  const clampedY = Math.max(margin, Math.min(y, window.innerHeight - menuHeight - margin));
  return {
    itemId,
    x: clampedX,
    y: clampedY,
    submenuPlacement: clampedX + menuWidth + submenuWidth + margin > window.innerWidth ? "left" : "right",
    submenuMaxHeight: Math.max(96, window.innerHeight - clampedY - margin),
  };
}

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
  const [quickAddUrl, setQuickAddUrl] = useState("");
  const [quickAdding, setQuickAdding] = useState(false);
  const [quickAddMessage, setQuickAddMessage] = useState<string | null>(null);
  const [quickAddError, setQuickAddError] = useState<string | null>(null);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [menuState, setMenuState] = useState<ItemContextMenuState | null>(null);

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

  useEffect(() => {
    if (!menuState) return;
    const close = () => setMenuState(null);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuState(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuState]);

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
    setMenuState(null);
    setMovingId(itemId);
    try {
      const result = await client.moveItem(itemId, folderId);
      setFeedback({ id: itemId, msg: `已收藏到知识库：${result.folder_name}` });
      setItems(await refreshInbox(keyword));
      await loadFolders();
      setTimeout(() => setFeedback(null), 2000);
    } catch {
      // silent
    } finally {
      setMovingId(null);
    }
  }

  async function handleDeleteItem(item: ApiItemSummary) {
    setMenuState(null);
    if (!window.confirm(`确定删除「${item.title}」吗？`)) return;
    setMovingId(item.id);
    setQuickAddError(null);
    setQuickAddMessage(null);
    try {
      await client.deleteItem(item.id);
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      await loadFolders();
      setQuickAddMessage("已删除");
      window.setTimeout(() => setQuickAddMessage(null), 2200);
    } catch (error) {
      setQuickAddError(error instanceof Error ? error.message : "删除失败");
    } finally {
      setMovingId(null);
    }
  }

  async function handleQuickAdd(event: FormEvent) {
    event.preventDefault();
    const url = normalizeQuickAddUrl(quickAddUrl);
    if (!url) {
      setQuickAddError("请先粘贴链接");
      return;
    }

    setQuickAdding(true);
    setQuickAddMessage(null);
    setQuickAddError(null);
    try {
      const sourceHint = isBilibiliUrl(url) ? "bilibili_video" : "article";
      const result = await client.importItem(url, sourceHint);
      setQuickAddUrl("");
      setShowQuickAdd(false);
      setQuickAddMessage(result.is_duplicate ? `已存在：${result.uid}` : `已加入稍后阅读：${result.uid}`);
      setItems(await refreshInbox(keyword));
      await loadFolders();
      window.setTimeout(() => setQuickAddMessage(null), 2600);
    } catch (error) {
      setQuickAddError(error instanceof Error ? error.message : "快速添加失败");
    } finally {
      setQuickAdding(false);
    }
  }

  const unreadCount = items.filter((i) => i.status === "completed" && !i.is_read).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Top bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.18)",
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

        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <button
            type="button"
            className="quick-add-trigger"
            onClick={() => {
              setQuickAddError(null);
              setQuickAddMessage(null);
              setShowQuickAdd(true);
            }}
          >
            <span className="icon icon-sm">add_link</span>
            快速添加
          </button>
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

      {showQuickAdd && (
        <div
          className="quick-add-modal-backdrop"
          role="presentation"
          onClick={() => {
            if (!quickAdding) setShowQuickAdd(false);
          }}
        >
          <form
            className="quick-add-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="quick-add-title"
            onSubmit={(event) => void handleQuickAdd(event)}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="quick-add-modal-header">
              <div>
                <h3 id="quick-add-title">快速添加</h3>
                <p>Bilibili 链接会按视频处理，其他链接按文章处理。</p>
              </div>
              <button
                type="button"
                className="topbar-icon-btn"
                aria-label="关闭"
                title="关闭"
                disabled={quickAdding}
                onClick={() => setShowQuickAdd(false)}
              >
                <span className="icon icon-sm">close</span>
              </button>
            </div>

            <label className="field">
              <span>链接地址</span>
              <input
                className="input"
                value={quickAddUrl}
                onChange={(event) => {
                  setQuickAddUrl(event.target.value);
                  setQuickAddError(null);
                  setQuickAddMessage(null);
                }}
                placeholder="https://example.com/article 或 https://www.bilibili.com/video/BV..."
                disabled={quickAdding}
                autoFocus
              />
            </label>

            {quickAddError && <div className="feedback feedback-error">{quickAddError}</div>}

            <div className="quick-add-modal-actions">
              <button type="button" className="btn btn-ghost btn-sm" disabled={quickAdding} onClick={() => setShowQuickAdd(false)}>
                取消
              </button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={quickAdding || !quickAddUrl.trim()}>
                <span className="icon icon-sm">{quickAdding ? "sync" : "add_link"}</span>
                {quickAdding ? "添加中…" : "加入稍后阅读"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {(quickAddMessage || quickAddError) && (
          <div
            className={`feedback ${quickAddError ? "feedback-error" : "feedback-success"}`}
            style={{ margin: "12px 28px 0" }}
          >
            {quickAddError ?? quickAddMessage}
          </div>
        )}

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
            menuState={menuState?.itemId === item.id ? menuState : null}
            onOpenMenu={(x, y) => setMenuState(createContextMenuState(item.id, x, y))}
            onMoveToFolder={(folderId) => void handleMoveToLibrary(item.id, folderId)}
            onDelete={() => void handleDeleteItem(item)}
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
  menuState,
  onOpenMenu,
  onMoveToFolder,
  onDelete,
}: {
  item: ApiItemSummary;
  folders: { id: string; name: string }[];
  isMoving: boolean;
  feedbackMsg: string | null;
  menuState: ItemContextMenuState | null;
  onOpenMenu: (x: number, y: number) => void;
  onMoveToFolder: (folderId: string) => void;
  onDelete: () => void;
}) {
  const navigate = useNavigate();

  const isVideo = item.content_type === "bilibili_video";
  const progress = normalizeProgress(item.progress_percent);
  const showProgress = progress > 0 && progress < 100;
  const readHref = `/items/${item.id}?from=inbox`;

  function handleMove(folderId: string) {
    onMoveToFolder(folderId);
  }


  return (
    <div
      style={{
        borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
        transition: "background 120ms ease",
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        onOpenMenu(e.clientX, e.clientY);
      }}
    >
      {/* Main row */}
      <div
        style={{ display: "flex", alignItems: "flex-start", gap: 0, padding: "0 28px", cursor: "pointer" }}
        onClick={() => navigate(readHref)}
        onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--surface-low)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = ""; }}
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
          <button
            type="button"
            className="topbar-icon-btn"
            aria-label="更多操作"
            title="更多操作"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onOpenMenu(e.clientX, e.clientY);
            }}
            style={{ width: 28, height: 28 }}
          >
            <span className="icon icon-sm">more_horiz</span>
          </button>
        </div>
      </div>

      {feedbackMsg && (
        <div style={{ padding: "0 28px 10px 50px", fontSize: 12, color: "var(--success)", fontWeight: 600 }}>
          ✓ {feedbackMsg}
        </div>
      )}

      {menuState && (
        <div
          className="item-context-menu"
          style={{ left: menuState.x, top: menuState.y }}
          onClick={(e) => e.stopPropagation()}
          role="menu"
        >
          <button type="button" className="context-menu-item" onClick={() => navigate(readHref)}>
            <span className="icon icon-sm">auto_stories</span>
            阅读
          </button>

          {folders.length > 0 && (
            <div className="context-menu-submenu">
              <button type="button" className="context-menu-item">
                <span className="icon icon-sm">drive_file_move</span>
                {isMoving ? "收藏中…" : "收藏到知识库"}
                <span className="icon icon-sm context-menu-arrow">chevron_right</span>
              </button>
              <div
                className={`item-context-submenu ${menuState.submenuPlacement === "left" ? "submenu-left" : ""}`}
                role="menu"
                style={{ maxHeight: menuState.submenuMaxHeight }}
              >
                {folders.map((folder) => (
                  <button
                    key={folder.id}
                    type="button"
                    className="context-menu-item"
                    disabled={isMoving}
                    onClick={() => handleMove(folder.id)}
                  >
                    <span className="icon icon-sm">folder</span>
                    {folder.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {folders.length === 0 && (
            <button type="button" className="context-menu-item" onClick={() => navigate("/library")}>
              <span className="icon icon-sm">create_new_folder</span>
              先创建收藏夹
            </button>
          )}

          {item.source_url && (
            <a className="context-menu-item" href={item.source_url} target="_blank" rel="noreferrer">
              <span className="icon icon-sm">open_in_new</span>
              打开原文
            </a>
          )}

          <button type="button" className="context-menu-item context-menu-danger" onClick={onDelete}>
            <span className="icon icon-sm">delete</span>
            删除
          </button>
        </div>
      )}
    </div>
  );
}
