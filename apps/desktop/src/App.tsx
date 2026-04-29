import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { createApiClient } from "./api";
import { ConnectPage } from "./pages/ConnectPage";
import { FeedPage } from "./pages/FeedPage";
import { ImportPage } from "./pages/ImportPage";
import { InboxPage } from "./pages/InboxPage";
import { ItemDetailPage } from "./pages/ItemDetailPage";
import { LibraryPage } from "./pages/LibraryPage";
import { PodcastsPage } from "./pages/PodcastsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useAppState } from "./state/appState";

type PrimaryContext = "feed" | "podcasts" | "inbox" | "library" | "import" | "settings";

function inferPrimaryContext(pathname: string, search: string): PrimaryContext {
  if (pathname === "/" || pathname === "/feed") return "feed";
  if (pathname === "/podcasts") return "podcasts";
  if (pathname === "/inbox") return "inbox";
  if (pathname === "/import") return "import";
  if (pathname === "/settings" || pathname === "/connect") return "settings";
  if (pathname === "/library" || pathname.startsWith("/folders/")) return "library";
  if (pathname.startsWith("/items/") || pathname.startsWith("/reader/")) {
    const from = new URLSearchParams(search).get("from");
    if (from === "inbox") return "inbox";
    if (from === "feed") return "feed";
    if (from === "podcasts") return "podcasts";
    if (from === "import") return "import";
  }
  return "library";
}

function isActive(pathname: string, to: string, ctx: PrimaryContext) {
  if (to === "/feed") return ctx === "feed";
  if (to === "/podcasts") return ctx === "podcasts";
  if (to === "/inbox") return ctx === "inbox";
  if (to === "/library") return ctx === "library";
  if (to === "/import") return ctx === "import";
  if (ctx === "settings") return false;
  return pathname === to || pathname.startsWith(`${to}/`);
}

function isSearchEnabled(pathname: string) {
  return ["/feed", "/podcasts", "/inbox", "/library"].includes(pathname) || pathname.startsWith("/folders/");
}

function searchPlaceholder(pathname: string) {
  if (!isSearchEnabled(pathname)) return "当前页面不支持搜索";
  if (pathname === "/feed") return "搜索订阅源…";
  if (pathname === "/podcasts") return "播客页内搜索…";
  if (pathname === "/inbox") return "搜索稍后阅读…";
  return "搜索知识库…";
}

function connectionLabel(state: "idle" | "checking" | "connected" | "unavailable") {
  switch (state) {
    case "checking": return "连接中";
    case "connected": return "服务端在线";
    case "unavailable": return "服务端不可用";
    default: return "等待连接";
  }
}

const navItems = [
  { to: "/feed", label: "订阅源", icon: "rss_feed", ctx: "feed" as PrimaryContext },
  { to: "/inbox", label: "稍后阅读", icon: "bookmarks", ctx: "inbox" as PrimaryContext },
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
  const [folderMessage, setFolderMessage] = useState<string | null>(null);
  const [folderError, setFolderError] = useState<string | null>(null);
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
    setFolderError(null);
    try {
      await client.createFolder(name);
      await loadFolders();
      setNewFolderName("");
      setShowNewFolder(false);
      setFolderMessage(`已创建收藏夹「${name}」`);
      window.setTimeout(() => setFolderMessage(null), 2500);
    } catch {
      setFolderError("创建收藏夹失败，请重试");
    } finally {
      setCreatingFolder(false);
    }
  }

  const libraryHeader = (
    <>
      <div className="sidebar-divider" />
      <div className="sidebar-section-header">
        <div className="sidebar-section-title">
          <span className="icon icon-sm">local_library</span>
          <span>知识库</span>
          {libraryCount > 0 && <span className="sidebar-section-count">{libraryCount}</span>}
        </div>
        <button
          type="button"
          className="sidebar-create-folder-btn"
          onClick={() => {
            setShowNewFolder((next) => !next);
            setFolderError(null);
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
              setFolderError(null);
            }}
            title="取消"
            aria-label="取消"
          >
            <span className="icon icon-sm">close</span>
          </button>
        </form>
      )}
      {folderMessage && <div className="sidebar-folder-feedback success">{folderMessage}</div>}
      {folderError && <div className="sidebar-folder-feedback error">{folderError}</div>}
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
                <Link
                  to="/library"
                  className={`nav-link ${ctx === "library" && location.pathname === "/library" ? "active" : ""}`}
                >
                  <span className="icon icon-sm">local_library</span>
                  <span className="nav-link-label" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    全部内容
                  </span>
                  {libraryCount > 0 && (
                    <span className="nav-link-badge">{libraryCount}</span>
                  )}
                </Link>
                {sidebarFolders.map((folder) => {
                  const active = location.pathname === `/folders/${folder.id}`;
                  return (
                    <Link
                      key={folder.id}
                      to={`/folders/${folder.id}`}
                      className={`nav-link ${active ? "active" : ""}`}
                    >
                      <span className="icon icon-sm">folder</span>
                      <span className="nav-link-label" style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {folder.name}
                      </span>
                      {folder.item_count > 0 && (
                        <span className="nav-link-badge">{folder.item_count}</span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </>
          )}

          {sidebarFolders.length === 0 && (
            <>
              {libraryHeader}
              <Link
                to="/library"
                className={`nav-link ${ctx === "library" ? "active" : ""}`}
              >
                <span className="icon icon-sm">local_library</span>
                <span className="nav-link-label">全部内容</span>
              </Link>
              <p className="sidebar-empty-hint">还没有收藏夹</p>
            </>
          )}

          <div className="sidebar-footer">
            <div className="sidebar-status">
              <div className={`status-dot status-${connectionState}`} />
              <span className="status-text">{connectionLabel(connectionState)}</span>
            </div>
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
            <Route path="/" element={<Navigate to="/feed" replace />} />
            <Route path="/feed" element={<FeedPage />} />
            <Route path="/podcasts" element={<PodcastsPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/folders/:folderId" element={<LibraryPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/reader/:itemId" element={<ItemDetailPage />} />
            <Route path="/items/:itemId" element={<ItemDetailPage />} />
            <Route path="/connect" element={<ConnectPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/feed" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
