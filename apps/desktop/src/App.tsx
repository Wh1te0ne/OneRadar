import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { ConnectPage } from "./pages/ConnectPage";
import { FeedPage } from "./pages/FeedPage";
import { ImportPage } from "./pages/ImportPage";
import { InboxPage } from "./pages/InboxPage";
import { ItemDetailPage } from "./pages/ItemDetailPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useAppState } from "./state/appState";

type PrimaryContext = "feed" | "inbox" | "library" | "import";

function inferPrimaryContext(pathname: string, search: string): PrimaryContext {
  if (pathname === "/" || pathname === "/feed") return "feed";
  if (pathname === "/inbox") return "inbox";
  if (pathname === "/import") return "import";
  if (pathname === "/library" || pathname.startsWith("/folders/")) return "library";
  if (pathname.startsWith("/items/") || pathname.startsWith("/reader/")) {
    const from = new URLSearchParams(search).get("from");
    if (from === "inbox") return "inbox";
    if (from === "feed") return "feed";
    if (from === "import") return "import";
  }
  return "library";
}

function isActive(pathname: string, to: string, ctx: PrimaryContext) {
  if (to === "/feed") return ctx === "feed";
  if (to === "/inbox") return ctx === "inbox";
  if (to === "/library") return ctx === "library";
  if (to === "/import") return ctx === "import";
  return pathname === to || pathname.startsWith(`${to}/`);
}

function isSearchEnabled(pathname: string) {
  return ["/feed", "/inbox", "/library"].includes(pathname) || pathname.startsWith("/folders/");
}

function searchPlaceholder(pathname: string) {
  if (!isSearchEnabled(pathname)) return "当前页面不支持搜索";
  if (pathname === "/feed") return "搜索订阅源…";
  if (pathname === "/inbox") return "搜索收件箱…";
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
  { to: "/feed",    label: "订阅源",    icon: "rss_feed",     ctx: "feed"    as PrimaryContext },
  { to: "/inbox",   label: "稍后阅读",  icon: "bookmarks",    ctx: "inbox"   as PrimaryContext },
  { to: "/library", label: "知识库",    icon: "local_library",ctx: "library" as PrimaryContext },
  { to: "/import",  label: "导入",      icon: "add_link",     ctx: "import"  as PrimaryContext },
];

export default function App() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { connectionState, folders, workspace } = useAppState();

  const inboxFolder = workspace?.default_inbox_folder ?? folders.find((f) => f.id === "inbox");
  const sidebarFolders = folders.filter((f) => f.id !== inboxFolder?.id);
  const settingsPath = connectionState === "connected" ? "/settings" : "/connect";
  const settingsActive = location.pathname === "/settings" || location.pathname === "/connect";
  const searchEnabled = isSearchEnabled(location.pathname);
  const searchValue = searchEnabled ? (searchParams.get("q") ?? "") : "";
  const ctx = inferPrimaryContext(location.pathname, location.search);

  function handleSearchChange(value: string) {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) { next.set("q", value); } else { next.delete("q"); }
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="app-shell">
      {/* ── Sidebar ── */}
      <aside className="sidebar">
        {/* Brand */}
        <div className="sidebar-brand">
          <div className="brand-icon">
            <span className="icon icon-lg">radar</span>
          </div>
          <div className="brand-text">
            <h1>OneRadar</h1>
            <p>Zen Archive</p>
          </div>
        </div>

        {/* Primary Nav */}
        <nav aria-label="主导航">
          {navItems.map((item) => {
            const active = isActive(location.pathname, item.to, ctx);
            return (
              <Link key={item.to} to={item.to} className={`nav-link ${active ? "active" : ""}`}>
                <span className="icon">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Folders */}
        {sidebarFolders.length > 0 && (
          <>
            <div className="sidebar-divider" />
            <div className="sidebar-section-label">文件夹</div>
            <div className="sidebar-folders">
              {sidebarFolders.map((folder) => {
                const active = location.pathname === `/folders/${folder.id}`;
                return (
                  <Link
                    key={folder.id}
                    to={`/folders/${folder.id}`}
                    className={`nav-link ${active ? "active" : ""}`}
                  >
                    <span className="icon icon-sm">folder</span>
                    <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
            <div className="sidebar-divider" />
            <div className="sidebar-section-label">文件夹</div>
            <p className="sidebar-empty-hint">还没有自定义文件夹</p>
          </>
        )}

        {/* Footer */}
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <div className={`status-dot status-${connectionState}`} />
            <span className="status-text">{connectionLabel(connectionState)}</span>
          </div>
        </div>
      </aside>

      {/* ── Main Panel ── */}
      <main className="main-panel">
        {/* Topbar */}
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

        {/* Page Content */}
        <div className="workspace-frame">
          <Routes>
            <Route path="/" element={<Navigate to="/feed" replace />} />
            <Route path="/feed" element={<FeedPage />} />
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
