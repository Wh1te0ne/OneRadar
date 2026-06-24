import { useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useSearchParams } from "react-router-dom";
import { ApiConsolePage } from "./pages/ApiConsolePage";
import { AuthPage } from "./pages/AuthPage";
import { ConnectPage } from "./pages/ConnectPage";
import { DailyNewsPage, DailyNewsSharePage } from "./pages/DailyNewsPage";
import { FeedPage } from "./pages/FeedPage";
import { LinkAnalysisPage } from "./pages/LinkAnalysisPage";
import { SettingsPage } from "./pages/SettingsPage";
import { Toast, type ToastState } from "./components/Toast";
import { MobileApp } from "./MobileApp";
import { useAppState } from "./state/appState";

type PrimaryContext = "daily" | "feed" | "analysis" | "api" | "settings";

function inferPrimaryContext(pathname: string, search: string): PrimaryContext {
  void search;
  if (pathname === "/" || pathname === "/daily") return "daily";
  if (pathname === "/feed") return "feed";
  if (pathname === "/analysis") return "analysis";
  if (pathname === "/api-console") return "api";
  if (pathname === "/settings" || pathname === "/connect") return "settings";
  return "daily";
}

function isActive(pathname: string, to: string, ctx: PrimaryContext) {
  if (to === "/daily") return ctx === "daily";
  if (to === "/feed") return ctx === "feed";
  if (to === "/analysis") return ctx === "analysis";
  if (to === "/api-console") return ctx === "api";
  if (ctx === "settings") return false;
  return pathname === to || pathname.startsWith(`${to}/`);
}

function isSearchEnabled(pathname: string) {
  return ["/daily", "/feed"].includes(pathname);
}

function searchPlaceholder(pathname: string) {
  if (!isSearchEnabled(pathname)) return "当前页面不支持搜索";
  if (pathname === "/daily") return "搜索每日新闻…";
  if (pathname === "/feed") return "搜索订阅源…";
  return "搜索…";
}

const navItems = [
  { to: "/daily", label: "每日新闻", icon: "newspaper", ctx: "daily" as PrimaryContext },
  { to: "/feed", label: "信息源", icon: "rss_feed", ctx: "feed" as PrimaryContext },
  { to: "/analysis", label: "链接分析", icon: "hub", ctx: "analysis" as PrimaryContext },
  { to: "/api-console", label: "调用接口", icon: "terminal", ctx: "api" as PrimaryContext },
];

function useIsMobileViewport() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 760px)").matches : false
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia("(max-width: 760px)");
    const update = () => setIsMobile(mediaQuery.matches);
    update();
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", update);
      return () => mediaQuery.removeEventListener("change", update);
    }
    mediaQuery.addListener(update);
    return () => mediaQuery.removeListener(update);
  }, []);

  return isMobile;
}

export default function App() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("oneradar.sidebar.collapsed") === "true");
  const [toast, setToast] = useState<ToastState>(null);
  const { authToken, connectionState, currentUser, logout, updateCheck, workspace } = useAppState();
  const isMobileViewport = useIsMobileViewport();

  const settingsPath = connectionState === "connected" ? "/settings" : "/connect";
  const settingsActive = location.pathname === "/settings" || location.pathname === "/connect";
  const searchEnabled = isSearchEnabled(location.pathname);
  const searchValue = searchEnabled ? (searchParams.get("q") ?? "") : "";
  const ctx = inferPrimaryContext(location.pathname, location.search);
  useEffect(() => {
    localStorage.setItem("oneradar.sidebar.collapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

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

  if (location.pathname.startsWith("/share/daily/")) {
    return (
      <Routes>
        <Route path="/share/daily/:shareKey/:date" element={<DailyNewsSharePage />} />
        <Route path="*" element={<Navigate to="/daily" replace />} />
      </Routes>
    );
  }

  if (!authToken && workspace?.requires_login !== false) {
    return <AuthPage />;
  }

  if (isMobileViewport) {
    return <MobileApp />;
  }

  return (
    <div className={`app-shell${sidebarCollapsed ? " app-shell-sidebar-collapsed" : ""}`}>
      <aside className={`sidebar${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
          <div className="sidebar-brand">
            <div className="brand-icon">
              <span className="icon icon-lg">radar</span>
            </div>
            <div className="brand-text">
              <h1>OneRadar</h1>
              <p>News Radar</p>
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

          <div className="sidebar-footer">
            <p className="sidebar-empty-hint">RSS、日报、临时分析和接口调用由 OneRadar 负责；长期笔记交给 Obsidian。</p>
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
            {updateCheck.status === "available" && <span className="topbar-update-dot" aria-label="有可用更新" />}
          </Link>
          {currentUser && (
            <button type="button" className="topbar-icon-btn" title={`退出 ${currentUser.username}`} aria-label="退出登录" onClick={logout}>
              <span className="icon">logout</span>
            </button>
          )}
        </div>

        <div className="workspace-frame">
          <Routes>
            <Route path="/" element={<Navigate to="/daily" replace />} />
            <Route path="/daily" element={<DailyNewsPage />} />
            <Route path="/feed" element={<FeedPage />} />
            <Route path="/analysis" element={<LinkAnalysisPage />} />
            <Route path="/api-console" element={<ApiConsolePage />} />
            <Route path="/connect" element={<ConnectPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/daily" replace />} />
          </Routes>
        </div>
      </main>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
