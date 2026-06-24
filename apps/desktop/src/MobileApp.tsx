import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { DailyNewsPage } from "./pages/DailyNewsPage";
import { FeedPage } from "./pages/FeedPage";
import { LinkAnalysisPage } from "./pages/LinkAnalysisPage";
import { SettingsPage } from "./pages/SettingsPage";

type MobileTab = "daily" | "feed" | "analysis" | "settings";
type MobileToast = { message: string; tone: "success" | "error" | "info" } | null;

function mobileTabFromPath(pathname: string): MobileTab {
  if (pathname.startsWith("/feed")) return "feed";
  if (pathname.startsWith("/analysis")) return "analysis";
  if (pathname.startsWith("/settings")) return "settings";
  return "daily";
}

function MobileBottomNav() {
  return (
    <nav className="mobile-bottom-nav" aria-label="移动端主导航">
      <NavLink to="/daily" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="icon icon-sm">newspaper</span>
        <span>日报</span>
      </NavLink>
      <NavLink to="/feed" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="icon icon-sm">rss_feed</span>
        <span>信息源</span>
      </NavLink>
      <NavLink to="/analysis" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="icon icon-sm">travel_explore</span>
        <span>分析</span>
      </NavLink>
      <NavLink to="/settings" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="icon icon-sm">tune</span>
        <span>设置</span>
      </NavLink>
    </nav>
  );
}

function MobileToastView({ toast, onClose }: { toast: MobileToast; onClose: () => void }) {
  if (!toast) return null;
  return (
    <button type="button" className={`mobile-toast mobile-toast-${toast.tone}`} onClick={onClose}>
      {toast.message}
    </button>
  );
}

export function MobileApp() {
  const location = useLocation();
  const [toast, setToast] = useState<MobileToast>(null);

  useEffect(() => {
    const handleToast = (event: Event) => {
      const detail = (event as CustomEvent<NonNullable<MobileToast>>).detail;
      if (!detail?.message) return;
      setToast(detail);
      window.setTimeout(() => setToast(null), 2600);
    };
    window.addEventListener("oneradar:toast", handleToast);
    return () => window.removeEventListener("oneradar:toast", handleToast);
  }, []);

  const activeTab = mobileTabFromPath(location.pathname);

  return (
    <div className={`mobile-app mobile-tab-${activeTab}`}>
      <main className="mobile-main">
        <Routes>
          <Route path="/" element={<Navigate to="/daily" replace />} />
          <Route path="/daily" element={<DailyNewsPage />} />
          <Route path="/feed" element={<FeedPage />} />
          <Route path="/analysis" element={<LinkAnalysisPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/daily" replace />} />
        </Routes>
      </main>
      <MobileBottomNav />
      <MobileToastView toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
