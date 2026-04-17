import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { createApiClient, readLocalBilibiliCookie, isDesktopTauri } from "../api";
import type { ApiBilibiliCookieParseResponse, ApiBilibiliIntegrationSettings, ApiImportResponse, NativeBilibiliCookieSource } from "../api";
import { useAppState } from "../state/appState";

type ImportMode = "auto" | "article" | "bilibili_video";
type EditableSecret = string | null;

function inferSourceHint(url: string, mode: ImportMode): string | undefined {
  if (mode === "article") return "article";
  if (mode === "bilibili_video") return "bilibili_video";
  if (url.includes("bilibili.com") || url.includes("b23.tv") || url.includes("bili22.cn") || url.includes("bili23.cn") || url.includes("bili2233.cn"))
    return "bilibili_video";
  return "article";
}

function formatDateTime(value?: string | null) {
  if (!value) return "未保存";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function bilibiliStatusText(s: ApiBilibiliIntegrationSettings | null) {
  if (!s) return "未读取";
  if (!s.is_enabled) return "已停用";
  if (s.ready_for_authenticated_fetch) return "已启用·可用";
  if (s.has_cookie_values) return "字段不完整";
  return "未配置";
}

export function ImportPage() {
  const { apiBaseUrl, loadFolders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const desktopAvailable = useMemo(() => isDesktopTauri(), []);

  const [importUrl, setImportUrl] = useState("");
  const [importMode, setImportMode] = useState<ImportMode>("auto");
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ApiImportResponse | null>(null);

  const [integration, setIntegration] = useState<ApiBilibiliIntegrationSettings | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [cookieEnabled, setCookieEnabled] = useState(false);
  const [cookieHeader, setCookieHeader] = useState<EditableSecret>(null);
  const [sessdata, setSessdata] = useState<EditableSecret>(null);
  const [biliJct, setBiliJct] = useState<EditableSecret>(null);
  const [buvid3, setBuvid3] = useState<EditableSecret>(null);
  const [parseResult, setParseResult] = useState<ApiBilibiliCookieParseResponse | null>(null);
  const [nativeReadBusy, setNativeReadBusy] = useState(false);
  const [nativeSource, setNativeSource] = useState<NativeBilibiliCookieSource | null>(null);

  async function loadIntegrationSettings() {
    setSettingsLoading(true); setSettingsError(null);
    try {
      const r = await client.getBilibiliIntegration();
      setIntegration(r); setCookieEnabled(r.is_enabled);
    } catch (e) {
      setIntegration(null);
      setSettingsError(e instanceof Error ? e.message : "读取 Bilibili 设置失败");
    } finally {
      setSettingsLoading(false);
    }
  }

  useEffect(() => { void loadIntegrationSettings(); }, [client]);

  async function handleImport(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const url = importUrl.trim();
    if (!url) { setImportError("请先粘贴一个链接。"); return; }
    setImportBusy(true); setImportError(null); setImportResult(null);
    try {
      const r = await client.importItem(url, inferSourceHint(url, importMode));
      setImportResult(r); setImportUrl(""); await loadFolders();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "导入失败");
    } finally {
      setImportBusy(false);
    }
  }

  async function handleParseCookie() {
    if (!cookieHeader?.trim()) { setSettingsError("先粘贴整段 Cookie，再执行解析。"); return; }
    setSettingsBusy(true); setSettingsError(null); setSettingsMessage(null);
    try {
      const r = await client.parseBilibiliCookie(cookieHeader);
      setParseResult(r); setSettingsMessage(`已识别 ${r.extracted_count} 个关键字段。`);
    } catch (e) {
      setParseResult(null); setSettingsError(e instanceof Error ? e.message : "Cookie 解析失败");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function handleSaveCookie(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSettingsBusy(true); setSettingsError(null); setSettingsMessage(null);
    try {
      const payload: { is_enabled: boolean; cookie_header?: string; sessdata?: string; bili_jct?: string; buvid3?: string } = { is_enabled: cookieEnabled };
      if (cookieHeader !== null) payload.cookie_header = cookieHeader;
      if (sessdata !== null) payload.sessdata = sessdata;
      if (biliJct !== null) payload.bili_jct = biliJct;
      if (buvid3 !== null) payload.buvid3 = buvid3;
      const r = await client.updateBilibiliIntegration(payload);
      setIntegration(r);
      setSettingsMessage(r.ready_for_authenticated_fetch ? "Bilibili 登录态 Cookie 已保存。" : "Bilibili Cookie 设置已更新。");
      setCookieHeader(null); setSessdata(null); setBiliJct(null); setBuvid3(null); setParseResult(null);
    } catch (e) {
      setSettingsError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function handleAutoReadAndSave() {
    if (!desktopAvailable) { setSettingsError("该功能仅在 OneRadar 桌面版可用。"); return; }
    setNativeReadBusy(true); setSettingsError(null); setSettingsMessage(null);
    try {
      const r = await readLocalBilibiliCookie();
      const selected = r.selected;
      if (!selected?.cookieHeader) throw new Error(r.message || "没有找到可用的 Bilibili Cookie。");
      const saved = await client.updateBilibiliIntegration({ is_enabled: true, cookie_header: selected.cookieHeader });
      setIntegration(saved); setCookieEnabled(true);
      setCookieHeader(null); setSessdata(null); setBiliJct(null); setBuvid3(null); setParseResult(null);
      setNativeSource(selected);
      setSettingsMessage(`已从 ${selected.browserName} / ${selected.profileName} 读取并保存。`);
    } catch (e) {
      setSettingsError(e instanceof Error ? e.message : "读取本机 Cookie 失败");
    } finally {
      setNativeReadBusy(false);
    }
  }

  async function handleClearCookie() {
    setSettingsBusy(true); setSettingsError(null); setSettingsMessage(null);
    try {
      const r = await client.updateBilibiliIntegration({ is_enabled: false, sessdata: "", bili_jct: "", buvid3: "" });
      setIntegration(r); setCookieEnabled(false);
      setCookieHeader(null); setSessdata(null); setBiliJct(null); setBuvid3(null); setParseResult(null); setNativeSource(null);
      setSettingsMessage("已清空服务端保存的 Bilibili Cookie。");
    } catch (e) {
      setSettingsError(e instanceof Error ? e.message : "清空失败");
    } finally {
      setSettingsBusy(false);
    }
  }

  // Detect URL type hint for display
  const detectedType = useMemo(() => {
    if (importMode !== "auto") return importMode;
    const u = importUrl.trim().toLowerCase();
    if (u.includes("bilibili.com") || u.includes("b23.tv")) return "bilibili_video";
    if (u.length > 10) return "article";
    return null;
  }, [importUrl, importMode]);

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <p className="page-eyebrow">导入</p>
        <h2 className="page-title">添加内容</h2>
        <p className="page-lead">粘贴链接，AI 自动判断类型并处理——文章提取正文，视频/播客生成大纲。</p>
      </div>

      {/* Import Hero + Status */}
      <div className="workspace-grid" style={{ marginBottom: 24 }}>
        {/* Import Form */}
        <div className="card">
          {/* Drop Zone Hero */}
          <div className="import-hero" style={{ marginBottom: 24 }}>
            <div className="import-hero-icon">
              <span className="icon icon-lg">
                {detectedType === "bilibili_video" ? "smart_display" : detectedType === "article" ? "article" : "add_link"}
              </span>
            </div>
            <h3 style={{ fontFamily: "Manrope, sans-serif", fontSize: 17, fontWeight: 700, color: "var(--on-surface)", margin: 0 }}>
              {detectedType === "bilibili_video" ? "识别为 B站视频" : detectedType === "article" ? "识别为文章" : "粘贴任意链接"}
            </h3>
            <p style={{ fontSize: 13, color: "var(--on-surface-v)", margin: 0 }}>
              支持文章、B站视频、播客音频
            </p>
          </div>

          <form className="stack" onSubmit={(e) => void handleImport(e)}>
            <div className="field">
              <label htmlFor="import-url">链接地址</label>
              <input
                id="import-url"
                className="input"
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                placeholder="https://www.bilibili.com/video/…  或  https://example.com/article…"
              />
            </div>
            <div className="field">
              <label htmlFor="import-mode">处理方式</label>
              <select
                id="import-mode"
                className="select"
                value={importMode}
                onChange={(e) => setImportMode(e.target.value as ImportMode)}
              >
                <option value="auto">自动识别</option>
                <option value="article">按文章处理</option>
                <option value="bilibili_video">按 B站视频处理</option>
              </select>
            </div>

            {/* Type hint badges */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {[
                { icon: "article", label: "文章", desc: "提取正文内容" },
                { icon: "smart_display", label: "B站视频", desc: "生成转写大纲" },
                { icon: "podcasts", label: "播客", desc: "提取音频大纲" },
              ].map((t) => (
                <div key={t.label} style={{
                  display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
                  background: "var(--surface-container)", borderRadius: "var(--radius-sm)",
                  flex: 1, minWidth: 100
                }}>
                  <span className="icon icon-sm" style={{ color: "var(--tertiary)" }}>{t.icon}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--on-surface)" }}>{t.label}</div>
                    <div style={{ fontSize: 11, color: "var(--outline)" }}>{t.desc}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="btn-group">
              <button className="btn btn-primary" type="submit" disabled={importBusy} style={{ flex: 1, justifyContent: "center" }}>
                <span className="icon icon-sm">{importBusy ? "sync" : "rocket_launch"}</span>
                {importBusy ? "导入中…" : "加入收件箱"}
              </button>
              <Link className="btn btn-ghost" to="/inbox">
                <span className="icon icon-sm">all_inbox</span>
                查看收件箱
              </Link>
            </div>
          </form>

          {importResult && (
            <div className="feedback feedback-success" style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 700, marginBottom: 6 }}>
                {importResult.is_duplicate ? "链接已存在" : "✓ 已创建导入任务"}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <span className="chip chip-success">UID {importResult.uid}</span>
                <span className="chip chip-success">状态 {importResult.status}</span>
                <span className="chip chip-success">位置 {importResult.folder_name}</span>
              </div>
              {importResult.is_duplicate && (
                <p style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>该链接已存在，复用 UID {importResult.existing_uid ?? importResult.uid}。</p>
              )}
            </div>
          )}
          {importError && <div className="feedback feedback-error" style={{ marginTop: 16 }}>{importError}</div>}
        </div>

        {/* Bilibili Status Rail */}
        <div className="card detail-rail" style={{ padding: 0, overflow: "hidden" }}>
          <div className="card-header" style={{ padding: "16px 20px", borderBottom: "1px solid rgba(172,179,183,0.15)" }}>
            <span className="card-title">B站授权</span>
            <span className={`chip ${integration?.ready_for_authenticated_fetch ? "chip-success" : "chip-neutral"}`} style={{ fontSize: 11 }}>
              {bilibiliStatusText(integration)}
            </span>
          </div>

          <div style={{ padding: "16px 20px 20px" }}>
            <div className="surface-callout" style={{ marginBottom: 16 }}>
              <h3>Bilibili 登录态</h3>
              <p style={{ fontSize: 13, color: "var(--on-surface-v)", margin: "4px 0 0" }}>
                {integration?.ready_for_authenticated_fetch
                  ? "当前配置可用于带 Cookie 的字幕抓取。"
                  : "配置后可抓取无公开字幕的视频。"}
              </p>
            </div>

            <div className="info-list" style={{ marginBottom: 16 }}>
              {[
                { label: "启用状态", value: integration?.is_enabled ? "已启用" : "未启用" },
                { label: "SESSDATA", value: integration?.sessdata_preview ?? "未保存" },
                { label: "bili_jct", value: integration?.bili_jct_preview ?? "未保存" },
                { label: "最后更新", value: formatDateTime(integration?.updated_at) },
              ].map((row) => (
                <div key={row.label} className="info-row">
                  <span className="info-row-label">{row.label}</span>
                  <span className="info-row-value">{row.value}</span>
                </div>
              ))}
            </div>

            {nativeSource && (
              <div className="feedback feedback-success" style={{ marginBottom: 12, fontSize: 12 }}>
                <span className="icon icon-sm" style={{ marginRight: 4 }}>check_circle</span>
                已从 {nativeSource.browserName} 读取
              </div>
            )}

            <button
              className="btn btn-primary btn-sm"
              type="button"
              onClick={() => void handleAutoReadAndSave()}
              disabled={nativeReadBusy || settingsBusy || !desktopAvailable}
              style={{ width: "100%", justifyContent: "center", marginBottom: 8 }}
            >
              <span className="icon icon-sm">{nativeReadBusy ? "sync" : "cookie"}</span>
              {nativeReadBusy ? "读取中…" : "从本机浏览器获取"}
            </button>

            {!desktopAvailable && (
              <p className="text-caption" style={{ marginBottom: 8 }}>当前是网页预览环境，无法访问本机浏览器 Cookie。</p>
            )}
          </div>
        </div>
      </div>

      {/* Bilibili Cookie Config Section */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: "linear-gradient(135deg, #00a1d6, #0089c0)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "white"
          }}>
            <span className="icon">play_circle</span>
          </div>
          <div>
            <h3 style={{ fontFamily: "Manrope, sans-serif", fontSize: 16, fontWeight: 700, margin: 0 }}>Bilibili Cookie 配置</h3>
            <p style={{ fontSize: 12, color: "var(--outline)", margin: "2px 0 0" }}>服务端私有保存，不会在界面回显明文</p>
          </div>
        </div>

        <form className="stack" onSubmit={(e) => void handleSaveCookie(e)}>
          <label className="checkbox-row">
            <input type="checkbox" checked={cookieEnabled} onChange={(e) => setCookieEnabled(e.target.checked)} />
            <span>启用带 Cookie 的字幕抓取</span>
          </label>

          <div className="field">
            <label htmlFor="cookie-header">整段 Cookie（推荐方式）</label>
            <textarea
              id="cookie-header"
              className="textarea"
              rows={3}
              value={cookieHeader ?? ""}
              onChange={(e) => setCookieHeader(e.target.value)}
              placeholder="粘贴浏览器中的整段 Cookie，系统会自动提取关键字段"
            />
          </div>

          {parseResult && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {[
                { label: "SESSDATA", ok: parseResult.extracted.sessdata.configured, preview: parseResult.extracted.sessdata.preview },
                { label: "bili_jct", ok: parseResult.extracted.bili_jct.configured, preview: parseResult.extracted.bili_jct.preview },
                { label: "buvid3", ok: parseResult.extracted.buvid3.configured, preview: parseResult.extracted.buvid3.preview },
              ].map((field) => (
                <span key={field.label} className={`chip ${field.ok ? "chip-success" : "chip-neutral"}`}>
                  {field.label}: {field.preview ?? "未识别"}
                </span>
              ))}
            </div>
          )}

          {/* Manual fields */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div className="field">
              <label htmlFor="sessdata">SESSDATA</label>
              <input id="sessdata" className="input" value={sessdata ?? ""} onChange={(e) => setSessdata(e.target.value)} placeholder="留空不修改" />
            </div>
            <div className="field">
              <label htmlFor="bili-jct">bili_jct</label>
              <input id="bili-jct" className="input" value={biliJct ?? ""} onChange={(e) => setBiliJct(e.target.value)} placeholder="留空不修改" />
            </div>
            <div className="field">
              <label htmlFor="buvid3">buvid3</label>
              <input id="buvid3" className="input" value={buvid3 ?? ""} onChange={(e) => setBuvid3(e.target.value)} placeholder="留空不修改" />
            </div>
          </div>

          <div className="btn-group">
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => void handleParseCookie()} disabled={settingsBusy || !cookieHeader?.trim()}>
              <span className="icon icon-sm">manage_search</span>
              解析 Cookie
            </button>
            <button className="btn btn-primary btn-sm" type="submit" disabled={settingsBusy}>
              <span className="icon icon-sm">save</span>
              {settingsBusy ? "保存中…" : "保存到服务端"}
            </button>
            <button className="btn btn-danger btn-sm" type="button" onClick={() => void handleClearCookie()} disabled={settingsBusy || nativeReadBusy}>
              <span className="icon icon-sm">delete_sweep</span>
              清空
            </button>
          </div>
        </form>

        {settingsLoading && <p className="text-meta" style={{ marginTop: 12 }}>正在读取服务端设置…</p>}
        {settingsMessage && <div className="feedback feedback-success" style={{ marginTop: 12 }}>{settingsMessage}</div>}
        {settingsError && <div className="feedback feedback-error" style={{ marginTop: 12 }}>{settingsError}</div>}
      </div>
    </div>
  );
}
