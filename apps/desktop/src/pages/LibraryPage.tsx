import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createApiClient } from "../api";
import type { ApiItemSummary } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Toast, type ToastState } from "../components/Toast";
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
  const menuHeight = 164;
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

export function LibraryPage() {
  const { folderId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const inboxFolderId = workspace?.default_inbox_folder?.id ?? "inbox";

  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [menuState, setMenuState] = useState<ItemContextMenuState | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [pendingDeleteItems, setPendingDeleteItems] = useState<ApiItemSummary[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [toast, setToast] = useState<ToastState>(null);

  const keyword = searchParams.get("q")?.trim() ?? "";
  const tagFilter = searchParams.get("tag")?.trim() ?? "";
  const folderEntries = useMemo(() => folders.filter((f) => f.id !== inboxFolderId), [folders, inboxFolderId]);
  const movableFolders = useMemo(() => folders.filter((f) => !f.is_builtin && f.id !== inboxFolderId), [folders, inboxFolderId]);

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
    return items.filter((i) =>
      !kw || [i.title, i.summary ?? "", i.folder_name, i.source_url, ...(i.tags ?? [])].join(" ").toLowerCase().includes(kw)
    );
  }, [items, keyword]);

  const selectedItems = useMemo(
    () => visibleItems.filter((item) => selectedIds.has(item.id)),
    [selectedIds, visibleItems],
  );

  function showToast(message: string, tone: NonNullable<ToastState>["tone"] = "info") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 2600);
  }

  function updateFilter(key: "tag", value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  }

  function requestDeleteItem(item: ApiItemSummary) {
    setMenuState(null);
    setPendingDeleteItems([item]);
  }

  function requestDeleteSelected() {
    if (selectedItems.length === 0) return;
    setMenuState(null);
    setPendingDeleteItems(selectedItems);
  }

  async function confirmDeleteItem() {
    if (pendingDeleteItems.length === 0) return;
    const itemsToDelete = pendingDeleteItems;
    setDeleteError(null);
    setDeletingId(itemsToDelete[0].id);
    try {
      await Promise.all(itemsToDelete.map((item) => client.deleteItem(item.id)));
      const deletedIds = new Set(itemsToDelete.map((item) => item.id));
      setItems((current) => current.filter((candidate) => !deletedIds.has(candidate.id)));
      setSelectedIds((current) => {
        const next = new Set(current);
        deletedIds.forEach((id) => next.delete(id));
        return next;
      });
      await loadFolders();
      setPendingDeleteItems([]);
      showToast(itemsToDelete.length > 1 ? `已移入最近删除：${itemsToDelete.length} 条` : "已移入最近删除", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "删除失败", "error");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleMoveToFolder(item: ApiItemSummary, targetFolderId: string) {
    setMenuState(null);
    setMovingId(item.id);
    setDeleteError(null);
    try {
      await client.moveItem(item.id, targetFolderId);
      setItems(await refreshLibrary(folderId, keyword));
      await loadFolders();
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      showToast("已移动到目标收藏夹", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "移动失败", "error");
    } finally {
      setMovingId(null);
    }
  }

  async function handleBulkMoveToFolder(targetFolderId: string) {
    if (selectedItems.length === 0) return;
    setMovingId("bulk");
    setDeleteError(null);
    try {
      await Promise.all(selectedItems.map((item) => client.moveItem(item.id, targetFolderId)));
      setItems(await refreshLibrary(folderId, keyword));
      await loadFolders();
      setSelectedIds(new Set());
      showToast(`已移动 ${selectedItems.length} 条内容`, "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "批量移动失败", "error");
    } finally {
      setMovingId(null);
    }
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
          {deleteError && (
            <div className="feedback feedback-error" style={{ margin: "12px 28px 0" }}>{deleteError}</div>
          )}

          {selectedItems.length > 0 && (
            <div className="bulk-action-bar">
              <strong>已选择 {selectedItems.length} 条</strong>
              {movableFolders.length > 0 && (
                <select
                  className="input"
                  style={{ width: 150, height: 32, fontSize: 12 }}
                  defaultValue=""
                  disabled={movingId === "bulk"}
                  onChange={(event) => {
                    const target = event.target.value;
                    event.currentTarget.value = "";
                    if (target) void handleBulkMoveToFolder(target);
                  }}
                >
                  <option value="" disabled>移动到</option>
                  {movableFolders.map((folder) => (
                    <option key={folder.id} value={folder.id}>{folder.name}</option>
                  ))}
                </select>
              )}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelectedIds(new Set())}>取消选择</button>
              <button type="button" className="btn btn-danger btn-sm" onClick={requestDeleteSelected}>
                <span className="icon icon-sm">delete</span>
                删除
              </button>
            </div>
          )}

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
            <LibraryRow
              key={item.id}
              item={item}
              folders={movableFolders.filter((folder) => folder.id !== item.folder_id)}
              isMoving={movingId === item.id}
              menuState={menuState?.itemId === item.id ? menuState : null}
              selected={selectedIds.has(item.id)}
              onToggleSelected={(checked) => {
                setSelectedIds((current) => {
                  const next = new Set(current);
                  if (checked) next.add(item.id);
                  else next.delete(item.id);
                  return next;
                });
              }}
              onOpenMenu={(x, y) => setMenuState(createContextMenuState(item.id, x, y))}
              onMoveToFolder={(targetFolderId) => void handleMoveToFolder(item, targetFolderId)}
              onDelete={() => requestDeleteItem(item)}
            />
          ))}
        </div>

        {pendingDeleteItems.length > 0 && (
          <ConfirmDialog
            title="移入最近删除"
            body={
              pendingDeleteItems.length > 1
                ? `确定将选中的 ${pendingDeleteItems.length} 条内容移入最近删除吗？内容会保留 7 天。`
                : `确定将「${pendingDeleteItems[0].title}」移入最近删除吗？内容会保留 7 天。`
            }
            confirmLabel="删除"
            danger
            busy={Boolean(deletingId)}
            onCancel={() => {
              if (!deletingId) setPendingDeleteItems([]);
            }}
            onConfirm={() => void confirmDeleteItem()}
          />
        )}
        <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}

function LibraryRow({
  item,
  folders,
  isMoving,
  menuState,
  selected,
  onToggleSelected,
  onOpenMenu,
  onMoveToFolder,
  onDelete,
}: {
  item: ApiItemSummary;
  folders: { id: string; name: string }[];
  isMoving: boolean;
  menuState: ItemContextMenuState | null;
  selected: boolean;
  onToggleSelected: (checked: boolean) => void;
  onOpenMenu: (x: number, y: number) => void;
  onMoveToFolder: (folderId: string) => void;
  onDelete: () => void;
}) {
  const navigate = useNavigate();
  const isVideo = item.content_type === "bilibili_video";
  const progress = normalizeProgress(item.progress_percent);
  const showProgress = progress > 0 && progress < 100;
  const readHref = `/items/${item.id}`;


  return (
    <div
      onContextMenu={(event) => {
        event.preventDefault();
        onOpenMenu(event.clientX, event.clientY);
      }}
    >
      <div
        style={{
          display: "flex", alignItems: "flex-start", gap: 0,
          padding: "0 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
          transition: "background 120ms ease",
          cursor: "pointer",
        }}
        onClick={() => navigate(readHref)}
        onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "var(--surface-container)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = ""; }}
      >
        <input
          type="checkbox"
          className="row-select-control"
          aria-label={`选择 ${item.title}`}
          checked={selected}
          onChange={(event) => onToggleSelected(event.target.checked)}
          onClick={(event) => event.stopPropagation()}
        />
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
          <button
            type="button"
            className="topbar-icon-btn"
            aria-label="更多操作"
            title="更多操作"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onOpenMenu(event.clientX, event.clientY);
            }}
            style={{ width: 28, height: 28 }}
          >
            <span className="icon icon-sm">more_horiz</span>
          </button>
        </div>
      </div>

      {menuState && (
        <div
          className="item-context-menu"
          style={{ left: menuState.x, top: menuState.y }}
          onClick={(event) => event.stopPropagation()}
          role="menu"
        >
          {folders.length > 0 && (
            <div className="context-menu-submenu">
              <button type="button" className="context-menu-item">
                <span className="icon icon-sm">drive_file_move</span>
                {isMoving ? "移动中…" : "移动到"}
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
                    onClick={() => onMoveToFolder(folder.id)}
                  >
                    <span className="icon icon-sm">folder</span>
                    {folder.name}
                  </button>
                ))}
              </div>
            </div>
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
