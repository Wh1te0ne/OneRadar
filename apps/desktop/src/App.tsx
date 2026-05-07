import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { createApiClient } from "./api";
import { ConnectPage } from "./pages/ConnectPage";
import { DailyNewsPage } from "./pages/DailyNewsPage";
import { FeedArticlePreviewPage } from "./pages/FeedArticlePreviewPage";
import { FeedPage } from "./pages/FeedPage";
import { ImportPage } from "./pages/ImportPage";
import { InboxPage } from "./pages/InboxPage";
import { ItemDetailPage } from "./pages/ItemDetailPage";
import { LibraryPage } from "./pages/LibraryPage";
import { PodcastsPage } from "./pages/PodcastsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TrashPage } from "./pages/TrashPage";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { Toast, type ToastState } from "./components/Toast";
import { useAppState } from "./state/appState";

type PrimaryContext = "daily" | "feed" | "podcasts" | "inbox" | "library" | "import" | "settings" | "trash";

function inferPrimaryContext(pathname: string, search: string): PrimaryContext {
  if (pathname === "/" || pathname === "/daily") return "daily";
  if (pathname === "/feed" || pathname.startsWith("/feed/")) return "feed";
  if (pathname === "/podcasts") return "podcasts";
  if (pathname === "/inbox") return "inbox";
  if (pathname === "/import") return "import";
  if (pathname === "/settings" || pathname === "/connect") return "settings";
  if (pathname === "/trash") return "trash";
  if (pathname === "/library" || pathname.startsWith("/folders/")) return "library";
  if (pathname.startsWith("/items/") || pathname.startsWith("/reader/")) {
    const from = new URLSearchParams(search).get("from");
    if (from === "inbox") return "inbox";
    if (from === "daily") return "daily";
    if (from === "feed") return "feed";
    if (from === "podcasts") return "podcasts";
    if (from === "import") return "import";
  }
  return "library";
}

function isActive(pathname: string, to: string, ctx: PrimaryContext) {
  if (to === "/daily") return ctx === "daily";
  if (to === "/feed") return ctx === "feed";
  if (to === "/podcasts") return ctx === "podcasts";
  if (to === "/inbox") return ctx === "inbox";
  if (to === "/library") return ctx === "library";
  if (to === "/trash") return ctx === "trash";
  if (to === "/import") return ctx === "import";
  if (ctx === "settings") return false;
  return pathname === to || pathname.startsWith(`${to}/`);
}

function isSearchEnabled(pathname: string) {
  return ["/daily", "/feed", "/podcasts", "/inbox", "/library"].includes(pathname) || pathname.startsWith("/folders/");
}

function searchPlaceholder(pathname: string) {
  if (!isSearchEnabled(pathname)) return "当前页面不支持搜索";
  if (pathname === "/daily") return "搜索每日新闻…";
  if (pathname === "/feed") return "搜索订阅源…";
  if (pathname === "/podcasts") return "播客页内搜索…";
  if (pathname === "/inbox") return "搜索稍后阅读…";
  return "搜索知识库…";
}

const navItems = [
  { to: "/daily", label: "每日新闻", icon: "newspaper", ctx: "daily" as PrimaryContext },
  { to: "/inbox", label: "稍后阅读", icon: "bookmarks", ctx: "inbox" as PrimaryContext },
  { to: "/feed", label: "订阅源", icon: "rss_feed", ctx: "feed" as PrimaryContext },
  { to: "/podcasts", label: "播客", icon: "podcasts", ctx: "podcasts" as PrimaryContext },
  { to: "/import", label: "Bilibili", icon: "smart_display", ctx: "import" as PrimaryContext },
];

export default function App() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("oneradar.sidebar.collapsed") === "true");
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [folderMenu, setFolderMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [renamingFolder, setRenamingFolder] = useState<{ id: string; name: string } | null>(null);
  const [renameFolderName, setRenameFolderName] = useState("");
  const [deletingFolder, setDeletingFolder] = useState<{ id: string; name: string; item_count: number } | null>(null);
  const [folderBusy, setFolderBusy] = useState(false);
  const [toast, setToast] = useState<ToastState>(null);
  const { apiBaseUrl, connectionState, folders, loadFolders, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);

  const inboxFolder = workspace?.default_inbox_folder ?? folders.find((f) => f.id === "inbox");
  const sidebarFolders = folders.filter((f) => f.id !== inboxFolder?.id);
  const libraryCount = sidebarFolders.reduce((sum, folder) => sum + folder.item_count, 0);
  const settingsPath = connectionState === "connected" ? "/settings" : "/connect";
  const settingsActive = location.pathname === "/settings" || location.pathname === "/connect";
  const searchEnabled = isSearchEnabled(location.pathname);
  const searchValue = searchEnabled ? (searchParams.get("q") ?? "") : "";
  const ctx = inferPrimaryContext(location.pathname, location.search);
  useEffect(() => {
    localStorage.setItem("oneradar.sidebar.collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (!folderMenu) return;
    const close = () => setFolderMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [folderMenu]);

  function showToast(message: string, tone: NonNullable<ToastState>["tone"] = "info") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 2600);
  }

  useEffect(() => {
    const handleToast = (event: Event) => {
      const detail = (event as CustomEvent<NonNullable<ToastState>>).detail;
      if (!detail?.message) return;
      showToast(detail.message, detail.tone ?? "info");
    };
    window.addEventListener("oneradar:toast", handleToast);
    return () => window.removeEventListener("oneradar:toast", handleToast);
  }, []);

  function handleSearchChange(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) {
      next.set("q", value);
    } else {
      next.delete("q");
    }
    setSearchParams(next, { replace: true });
  }

  async function handleCreateFolder(e: FormEvent) {
    e.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;

    setCreatingFolder(true);
    try {
      await client.createFolder(name);
      await loadFolders();
      setNewFolderName("");
      setShowNewFolder(false);
      showToast(`已创建收藏夹「${name}」`, "success");
    } catch {
      showToast("创建收藏夹失败，请重试", "error");
    } finally {
      setCreatingFolder(false);
    }
  }

  async function handleRenameFolder(e: FormEvent) {
    e.preventDefault();
    if (!renamingFolder) return;
    const name = renameFolderName.trim();
    if (!name) return;
    setFolderBusy(true);
    try {
      await client.updateFolder(renamingFolder.id, name);
      await loadFolders();
      setRenamingFolder(null);
      setRenameFolderName("");
      showToast(`已重命名为「${name}」`, "success");
    } catch {
      showToast("重命名失败，请重试", "error");
    } finally {
      setFolderBusy(false);
    }
  }

  async function handleDeleteFolder() {
    if (!deletingFolder) return;
    setFolderBusy(true);
    try {
      const result = await client.deleteFolder(deletingFolder.id);
      await loadFolders();
      setDeletingFolder(null);
      showToast(result.moved_item_count > 0 ? `已删除收藏夹，${result.moved_item_count} 条内容移回稍后阅读` : "已删除收藏夹", "success");
    } catch {
      showToast("删除收藏夹失败，请重试", "error");
    } finally {
      setFolderBusy(false);
    }
  }

  const libraryHeader = (
    <>
      <div className="sidebar-divider" />
      <div className={`sidebar-section-header ${ctx === "library" && location.pathname === "/library" ? "active" : ""}`}>
        <Link to="/library" className="sidebar-section-link" aria-label="知识库">
          <span className="icon icon-sm">local_library</span>
          <span className="sidebar-section-text">知识库</span>
          {libraryCount > 0 && <span className="sidebar-section-count">{libraryCount}</span>}
        </Link>
        <button
          type="button"
          className="sidebar-create-folder-btn"
          onClick={() => {
            setShowNewFolder((next) => !next);
          }}
          aria-label="新建收藏夹"
          title="新建收藏夹"
        >
          <span className="icon icon-sm">add</span>
        </button>
      </div>
      {showNewFolder && (
        <form className="sidebar-create-folder-form" onSubmit={(e) => void handleCreateFolder(e)}>
          <input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="新建收藏夹"
            autoFocus
          />
          <button type="submit" disabled={creatingFolder || !newFolderName.trim()} title="创建收藏夹" aria-label="创建收藏夹">
            <span className="icon icon-sm">{creatingFolder ? "sync" : "check"}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setShowNewFolder(false);
              setNewFolderName("");
            }}
            title="取消"
            aria-label="取消"
          >
            <span className="icon icon-sm">close</span>
          </button>
        </form>
      )}
    </>
  );

  return (
    <div className={`app-shell${sidebarCollapsed ? " app-shell-sidebar-collapsed" : ""}`}>
      <aside className={`sidebar${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
          <div className="sidebar-brand">
            <div className="brand-icon">
              <span className="icon icon-lg">radar</span>
            </div>
            <div className="brand-text">
              <h1>OneRadar</h1>
              <p>Zen Archive</p>
            </div>
            <button
              type="button"
              className="sidebar-collapse-btn"
              onClick={() => setSidebarCollapsed((next) => !next)}
              aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
              title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
            >
              <span className="icon icon-sm">{sidebarCollapsed ? "keyboard_double_arrow_right" : "keyboard_double_arrow_left"}</span>
            </button>
          </div>

          <nav aria-label="主导航">
            {navItems.map((item) => {
              const active = isActive(location.pathname, item.to, ctx);
              return (
                <Link key={item.to} to={item.to} className={`nav-link ${active ? "active" : ""}`}>
                  <span className="icon">{item.icon}</span>
                  <span className="nav-link-label">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {sidebarFolders.length > 0 && (
            <>
              {libraryHeader}
              <div className="sidebar-folders">
                {sidebarFolders.map((folder) => {
                  const active = location.pathname === `/folders/${folder.id}`;
                  return (
                    <div
                      key={folder.id}
                      className={`nav-link sidebar-folder-row ${active ? "active" : ""}`}
                    >
                      <Link to={`/folders/${folder.id}`} className="sidebar-folder-link">
                        <span className="icon icon-sm">folder</span>
                        <span className="nav-link-label" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {folder.name}
                        </span>
                        {folder.item_count > 0 && (
                          <span className="nav-link-badge">{folder.item_count}</span>
                        )}
                      </Link>
                      <button
                        type="button"
                        className="sidebar-folder-menu-btn"
                        aria-label="收藏夹操作"
                        title="收藏夹操作"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          const rect = event.currentTarget.getBoundingClientRect();
                          setFolderMenu((current) => current?.id === folder.id ? null : {
                            id: folder.id,
                            x: Math.min(rect.right + 6, window.innerWidth - 192),
                            y: Math.min(rect.top, window.innerHeight - 112),
                          });
                        }}
                      >
                        <span className="icon icon-sm">more_horiz</span>
                      </button>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {sidebarFolders.length === 0 && (
            <>
              {libraryHeader}
              <p className="sidebar-empty-hint">还没有收藏夹</p>
            </>
          )}

          <div className="sidebar-footer">
            <Link to="/trash" className={`nav-link sidebar-footer-link ${ctx === "trash" ? "active" : ""}`}>
              <span className="icon">delete</span>
              <span className="nav-link-label">最近删除</span>
            </Link>
          </div>
      </aside>

      <main className="main-panel">
        <div className="shell-topbar">
          <div className="topbar-spacer" />
          <label className="shell-search" aria-label="搜索">
            <span className="icon icon-sm" style={{ color: "var(--outline)", flexShrink: 0 }}>search</span>
            <input
              type="search"
              value={searchValue}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder={searchPlaceholder(location.pathname)}
              disabled={!searchEnabled}
            />
          </label>
          <Link
            to={settingsPath}
            className={`topbar-icon-btn ${settingsActive ? "active" : ""}`}
            aria-label="设置"
          >
            <span className="icon">settings</span>
          </Link>
        </div>

        <div className="workspace-frame">
          <Routes>
            <Route path="/" element={<Navigate to="/daily" replace />} />
            <Route path="/daily" element={<DailyNewsPage />} />
            <Route path="/feed" element={<FeedPage />} />
            <Route path="/feed/preview" element={<FeedArticlePreviewPage />} />
            <Route path="/podcasts" element={<PodcastsPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/trash" element={<TrashPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/folders/:folderId" element={<LibraryPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/reader/:itemId" element={<ItemDetailPage />} />
            <Route path="/items/:itemId" element={<ItemDetailPage />} />
            <Route path="/connect" element={<ConnectPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/daily" replace />} />
          </Routes>
        </div>
      </main>
      {folderMenu && (() => {
        const folder = sidebarFolders.find((candidate) => candidate.id === folderMenu.id);
        if (!folder) return null;
        return (
          <div
            className="sidebar-folder-menu"
            style={{ left: folderMenu.x, top: folderMenu.y }}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="context-menu-item"
              onClick={() => {
                setFolderMenu(null);
                setRenamingFolder({ id: folder.id, name: folder.name });
                setRenameFolderName(folder.name);
              }}
            >
              <span className="icon icon-sm">edit</span>
              重命名
            </button>
            <button
              type="button"
              className="context-menu-item context-menu-danger"
              onClick={() => {
                setFolderMenu(null);
                setDeletingFolder({ id: folder.id, name: folder.name, item_count: folder.item_count });
              }}
            >
              <span className="icon icon-sm">delete</span>
              删除收藏夹
            </button>
          </div>
        );
      })()}
      {renamingFolder && (
        <div className="confirm-dialog-backdrop" role="presentation" onClick={() => !folderBusy && setRenamingFolder(null)}>
          <form
            className="confirm-dialog folder-rename-dialog"
            role="dialog"
            aria-modal="true"
            onSubmit={(event) => void handleRenameFolder(event)}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-dialog-icon">
              <span className="icon icon-sm">folder</span>
            </div>
            <div className="confirm-dialog-copy">
              <h3>重命名收藏夹</h3>
              <label className="field">
                <span>收藏夹名称</span>
                <input
                  className="input"
                  value={renameFolderName}
                  onChange={(event) => setRenameFolderName(event.target.value)}
                  disabled={folderBusy}
                  autoFocus
                />
              </label>
            </div>
            <div className="confirm-dialog-actions">
              <button type="button" className="btn btn-ghost btn-sm" disabled={folderBusy} onClick={() => setRenamingFolder(null)}>取消</button>
              <button type="submit" className="btn btn-primary btn-sm" disabled={folderBusy || !renameFolderName.trim()}>
                <span className="icon icon-sm">{folderBusy ? "sync" : "check"}</span>
                保存
              </button>
            </div>
          </form>
        </div>
      )}
      {deletingFolder && (
        <ConfirmDialog
          title="删除收藏夹"
          body={
            deletingFolder.item_count > 0
              ? `确定删除「${deletingFolder.name}」吗？其中 ${deletingFolder.item_count} 条内容会移回稍后阅读。`
              : `确定删除「${deletingFolder.name}」吗？`
          }
          confirmLabel="删除"
          danger
          busy={folderBusy}
          onCancel={() => {
            if (!folderBusy) setDeletingFolder(null);
          }}
          onConfirm={() => void handleDeleteFolder()}
        />
      )}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
