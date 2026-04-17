import { FormEvent, useEffect, useMemo, useState } from "react";
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

function sortByRecent(items: ApiItemSummary[]) {
  return [...items].sort((a, b) => {
    const at = Date.parse(a.updated_at ?? a.created_at ?? "");
    const bt = Date.parse(b.updated_at ?? b.created_at ?? "");
    return (Number.isNaN(bt) ? 0 : bt) - (Number.isNaN(at) ? 0 : at);
  });
}

export function LibraryPage() {
  const { folderId } = useParams();
  const [searchParams] = useSearchParams();
  const { apiBaseUrl, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const inboxFolderId = workspace?.default_inbox_folder?.id ?? "inbox";

  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const keyword = searchParams.get("q")?.trim() ?? "";
  const folderEntries = useMemo(() => folders.filter((f) => f.id !== inboxFolderId), [folders, inboxFolderId]);

  async function refreshLibrary(activeFolderId?: string, kw = "") {
    const r = await client.listItems({ pageSize: 200, folderId: activeFolderId, inboxOnly: false, keyword: kw || undefined });
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
  }, [client, folderId, keyword]);

  const visibleItems = useMemo(() => {
    const kw = keyword.toLowerCase();
    return items.filter((i) =>
      !kw || [i.title, i.summary ?? "", i.folder_name, i.source_url].join(" ").toLowerCase().includes(kw)
    );
  }, [items, keyword]);

  async function handleCreateFolder(e: FormEvent) {
    e.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;
    setCreatingFolder(true); setActionError(null);
    try {
      await client.createFolder(name);
      setNewFolderName(""); setShowNewFolder(false);
      await loadFolders();
      setFeedback(`已创建文件夹「${name}」`);
      setTimeout(() => setFeedback(null), 2500);
    } catch {
      setActionError("创建失败，请重试");
    } finally {
      setCreatingFolder(false);
    }
  }

  const currentFolder = folderEntries.find((f) => f.id === folderId);

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left: folder sidebar */}
      <div style={{
        width: 200, flexShrink: 0, borderRight: "1px solid rgba(172,179,183,0.18)",
        display: "flex", flexDirection: "column", overflowY: "auto", padding: "16px 12px",
        gap: 2,
      }}>
        {/* All items */}
        <Link
          to="/library"
          style={{
            display: "flex", alignItems: "center", gap: 9, padding: "9px 10px",
            borderRadius: "var(--radius-sm)", fontSize: 13.5, fontWeight: !folderId ? 600 : 500,
            color: !folderId ? "var(--primary)" : "var(--on-surface-v)",
            background: !folderId ? "var(--surface-lowest)" : "transparent",
            boxShadow: !folderId ? "var(--shadow-card)" : "none",
            textDecoration: "none", transition: "all 140ms ease",
          }}
          onMouseEnter={(e) => { if (folderId) (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-container)"; }}
          onMouseLeave={(e) => { if (folderId) (e.currentTarget as HTMLAnchorElement).style.background = ""; }}
        >
          <span className="icon icon-sm">inbox_all</span>
          全部内容
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--outline)", fontWeight: 400 }}>
            {folderEntries.reduce((sum, f) => sum + f.item_count, 0)}
          </span>
        </Link>

        {/* Divider */}
        <div style={{ height: 1, background: "rgba(172,179,183,0.18)", margin: "8px 4px" }} />

        {/* Folder list */}
        {folderEntries.map((f) => (
          <Link
            key={f.id}
            to={`/folders/${f.id}`}
            style={{
              display: "flex", alignItems: "center", gap: 9, padding: "9px 10px",
              borderRadius: "var(--radius-sm)", fontSize: 13.5,
              fontWeight: folderId === f.id ? 600 : 500,
              color: folderId === f.id ? "var(--primary)" : "var(--on-surface-v)",
              background: folderId === f.id ? "var(--surface-lowest)" : "transparent",
              boxShadow: folderId === f.id ? "var(--shadow-card)" : "none",
              textDecoration: "none", transition: "all 140ms ease",
              overflow: "hidden",
            }}
            onMouseEnter={(e) => { if (folderId !== f.id) (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-container)"; }}
            onMouseLeave={(e) => { if (folderId !== f.id) (e.currentTarget as HTMLAnchorElement).style.background = ""; }}
          >
            <span className="icon icon-sm" style={{ flexShrink: 0 }}>folder</span>
            <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {f.name}
            </span>
            {f.item_count > 0 && (
              <span style={{ fontSize: 11, color: "var(--outline)", fontWeight: 400, flexShrink: 0 }}>
                {f.item_count}
              </span>
            )}
          </Link>
        ))}

        {folderEntries.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--outline)", padding: "4px 10px", lineHeight: 1.5, fontStyle: "italic" }}>
            还没有文件夹
          </p>
        )}

        {/* New folder */}
        <div style={{ marginTop: 8 }}>
          {!showNewFolder ? (
            <button
              type="button"
              onClick={() => setShowNewFolder(true)}
              style={{
                display: "flex", alignItems: "center", gap: 8, padding: "8px 10px",
                width: "100%", border: "1.5px dashed rgba(172,179,183,0.4)", borderRadius: "var(--radius-sm)",
                background: "transparent", cursor: "pointer", fontSize: 13, color: "var(--outline)",
                transition: "all 140ms ease",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--primary)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--primary)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(172,179,183,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--outline)"; }}
            >
              <span className="icon icon-sm">create_new_folder</span>
              新建文件夹
            </button>
          ) : (
            <form onSubmit={(e) => void handleCreateFolder(e)} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <input
                className="input"
                style={{ fontSize: 13, padding: "7px 10px" }}
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="文件夹名称"
                autoFocus
              />
              <div style={{ display: "flex", gap: 5 }}>
                <button className="btn btn-primary btn-sm" type="submit" disabled={creatingFolder} style={{ flex: 1, justifyContent: "center", fontSize: 12 }}>
                  {creatingFolder ? "创建中…" : "创建"}
                </button>
                <button className="btn btn-ghost btn-sm" type="button" onClick={() => { setShowNewFolder(false); setNewFolderName(""); }} style={{ fontSize: 12 }}>
                  取消
                </button>
              </div>
              {actionError && <p style={{ fontSize: 11, color: "var(--error)", margin: 0 }}>{actionError}</p>}
            </form>
          )}
        </div>

        {feedback && (
          <p style={{ fontSize: 11.5, color: "var(--success)", fontWeight: 600, padding: "4px 10px", margin: 0 }}>
            ✓ {feedback}
          </p>
        )}
      </div>

      {/* Right: article list */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {/* Top bar */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 28px", borderBottom: "1px solid rgba(172,179,183,0.18)",
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
              <h3>{keyword ? "没有匹配内容" : folderId ? "这个文件夹还是空的" : "知识库还是空的"}</h3>
              <p>{keyword ? "换个关键词试试。" : "从「稍后阅读」存入文件夹后，内容会出现在这里。"}</p>
            </div>
          )}

          {visibleItems.map((item) => (
            <LibraryRow key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}

function LibraryRow({ item }: { item: ApiItemSummary }) {
  const isVideo = item.content_type === "bilibili_video";

  return (
    <Link
      to={`/items/${item.id}`}
      style={{ display: "block", textDecoration: "none" }}
    >
      <div
        style={{
          display: "flex", alignItems: "flex-start", gap: 0,
          padding: "0 28px", borderBottom: "1px solid rgba(172,179,183,0.12)",
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
