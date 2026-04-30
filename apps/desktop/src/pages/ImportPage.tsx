import { FormEvent, useEffect, useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { createApiClient } from "../api";
import type {
  ApiBilibiliIntegrationSettings,
  ApiBilibiliPreviewResponse,
  ApiBilibiliQrcodeGenerateResponse,
  ApiBilibiliQrcodePollResponse,
  ApiImportResponse
} from "../api";
import { useAppState } from "../state/appState";
import { displayFolderName } from "../utils/display";

type QrcodeStatus = ApiBilibiliQrcodePollResponse["state"] | "idle" | "creating";

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

function qrcodeStatusText(status: QrcodeStatus, message?: string | null) {
  if (status === "creating") return "正在生成二维码…";
  if (status === "waiting") return "等待扫码";
  if (status === "scanned") return "已扫码，等待手机确认";
  if (status === "confirmed") return "已登录并保存";
  if (status === "expired") return "二维码已失效";
  if (status === "failed") return message || "登录状态获取失败";
  return "未开始";
}

function apiRootUrl(baseUrl: string) {
  const normalized = baseUrl.trim().replace(/\/+$/, "");
  return normalized.endsWith("/api") ? normalized.slice(0, -4) : normalized;
}

function bilibiliCoverSrc(baseUrl: string, coverUrl: string) {
  const params = new URLSearchParams({ url: coverUrl });
  return `${apiRootUrl(baseUrl)}/api/items/bilibili/cover?${params.toString()}`;
}

export function ImportPage() {
  const { apiBaseUrl, loadFolders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);

  const [importUrl, setImportUrl] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ApiImportResponse | null>(null);
  const [preview, setPreview] = useState<ApiBilibiliPreviewResponse | null>(null);

  const [integration, setIntegration] = useState<ApiBilibiliIntegrationSettings | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [qrcodePayload, setQrcodePayload] = useState<ApiBilibiliQrcodeGenerateResponse | null>(null);
  const [qrcodeStatus, setQrcodeStatus] = useState<QrcodeStatus>("idle");
  const [qrcodeMessage, setQrcodeMessage] = useState<string | null>(null);
  const [qrcodeExpiresAt, setQrcodeExpiresAt] = useState<number | null>(null);

  async function loadIntegrationSettings() {
    setSettingsLoading(true); setSettingsError(null);
    try {
      const r = await client.getBilibiliIntegration();
      setIntegration(r);
    } catch (e) {
      setIntegration(null);
      setSettingsError(e instanceof Error ? e.message : "读取 Bilibili 设置失败");
    } finally {
      setSettingsLoading(false);
    }
  }

  useEffect(() => { void loadIntegrationSettings(); }, [client]);

  useEffect(() => {
    if (!qrcodePayload || !["waiting", "scanned"].includes(qrcodeStatus)) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await client.pollBilibiliQrcode(qrcodePayload.qrcode_key);
        if (cancelled) return;
        setQrcodeStatus(r.state);
        setQrcodeMessage(r.message);
        if (r.saved_cookie) {
          setIntegration(r.saved_cookie);
          setSettingsMessage("Bilibili 扫码登录成功，Cookie 已保存。");
        }
      } catch (e) {
        if (cancelled) return;
        setQrcodeStatus("failed");
        setQrcodeMessage(e instanceof Error ? e.message : "二维码登录轮询失败");
      }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    void poll();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [client, qrcodePayload, qrcodeStatus]);

  useEffect(() => {
    if (!qrcodeExpiresAt || !["waiting", "scanned"].includes(qrcodeStatus)) return;
    const timer = window.setInterval(() => {
      if (Date.now() >= qrcodeExpiresAt) {
        setQrcodeStatus("expired");
        setQrcodeMessage("二维码已过期，请重新获取。");
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [qrcodeExpiresAt, qrcodeStatus]);

  async function handlePreview(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const url = importUrl.trim();
    if (!url) { setImportError("请先粘贴一个链接。"); return; }
    setPreviewBusy(true); setImportError(null); setImportResult(null);
    try {
      const r = await client.previewBilibiliVideo(url);
      setPreview(r);
      setImportUrl(r.normalized_url);
    } catch (e) {
      setPreview(null);
      setImportError(e instanceof Error ? e.message : "视频预览失败");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function handleConfirmImport() {
    if (!preview) return;
    setConfirmBusy(true); setImportError(null); setImportResult(null);
    try {
      const r = await client.importItem(preview.normalized_url, "bilibili_video");
      setImportResult(r);
      await loadFolders();
    } catch (e) {
      setImportError(e instanceof Error ? e.message : "加入稍后阅读失败");
    } finally {
      setConfirmBusy(false);
    }
  }

  async function handleCreateQrcode() {
    setSettingsBusy(true); setSettingsError(null); setSettingsMessage(null);
    setQrcodeStatus("creating"); setQrcodeMessage(null);
    try {
      const r = await client.createBilibiliQrcode();
      setQrcodePayload(r);
      setQrcodeExpiresAt(Date.now() + r.expires_in_seconds * 1000);
      setQrcodeStatus("waiting");
      setQrcodeMessage("请使用 Bilibili 手机 App 扫码确认登录。");
    } catch (e) {
      setQrcodePayload(null);
      setQrcodeExpiresAt(null);
      setQrcodeStatus("failed");
      setQrcodeMessage(e instanceof Error ? e.message : "二维码生成失败");
      setSettingsError(e instanceof Error ? e.message : "二维码生成失败");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function handleClearCookie() {
    setSettingsBusy(true); setSettingsError(null); setSettingsMessage(null);
    try {
      const r = await client.updateBilibiliIntegration({
        is_enabled: false,
        sessdata: "",
        bili_jct: "",
        buvid3: ""
      });
      setIntegration(r);
      setSettingsMessage("已清空服务端保存的 Bilibili Cookie。");
    } catch (e) {
      setSettingsError(e instanceof Error ? e.message : "清空失败");
    } finally {
      setSettingsBusy(false);
    }
  }

  return (
    <div className="page bilibili-import-page">
      <div className="page-header">
        <p className="page-eyebrow">Bilibili</p>
        <h2 className="page-title">视频解析</h2>
        <p className="page-lead">粘贴 Bilibili 视频链接，系统会优先获取字幕；没有可用字幕时再进入音频转写，并保留时间戳。</p>
      </div>

      <div className="workspace-grid bilibili-import-grid" style={{ marginBottom: 24 }}>
        <div className="card bilibili-import-card">
          <div className="card-header bilibili-import-header">
            <span className="card-title">输入链接</span>
            <span className="chip chip-neutral">bilibili.com / b23.tv</span>
          </div>

          <form className="bilibili-url-form" onSubmit={(e) => void handlePreview(e)}>
            <div className="field bilibili-url-field">
              <label htmlFor="import-url">链接地址</label>
              <input
                id="import-url"
                className="input"
                value={importUrl}
                onChange={(e) => {
                  setImportUrl(e.target.value);
                  setImportResult(null);
                }}
                placeholder="https://www.bilibili.com/video/BV…"
              />
            </div>
            <button className="btn btn-bili-primary" type="submit" disabled={previewBusy}>
              <span className="icon icon-sm">{previewBusy ? "sync" : "manage_search"}</span>
              {previewBusy ? "解析中…" : "解析视频"}
            </button>
          </form>

          {importError && <div className="feedback feedback-error" style={{ marginTop: 16 }}>{importError}</div>}
        </div>

        <div className="card detail-rail bilibili-auth-card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="card-header" style={{ padding: "16px 20px", borderBottom: "1px solid rgba(var(--outline-rgb),0.15)" }}>
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
                  ? "当前登录态会在服务端保留，直到 B站失效或手动清除。"
                  : "扫码后会保存服务端登录态，过期后重新扫码即可。"}
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

            <div className="bilibili-qrcode-box">
              {qrcodePayload && ["waiting", "scanned", "confirmed"].includes(qrcodeStatus) ? (
                <QRCodeSVG value={qrcodePayload.url} size={148} level="M" includeMargin />
              ) : (
                <div className="bilibili-qrcode-placeholder">
                  <span className="icon icon-lg">qr_code_2</span>
                </div>
              )}
              <div className="text-caption" style={{ textAlign: "center", marginTop: 8 }}>
                {qrcodeStatusText(qrcodeStatus, qrcodeMessage)}
              </div>
            </div>

            <button
              className="btn btn-bili-primary btn-sm"
              type="button"
              onClick={() => void handleCreateQrcode()}
              disabled={settingsBusy || qrcodeStatus === "creating"}
              style={{ width: "100%", justifyContent: "center", marginBottom: 8 }}
            >
              <span className="icon icon-sm">{qrcodeStatus === "creating" ? "sync" : "qr_code_scanner"}</span>
              {qrcodePayload && qrcodeStatus !== "expired" ? "重新获取二维码" : "扫码获取 Cookie"}
            </button>

            <button
              className="btn btn-danger btn-sm"
              type="button"
              onClick={() => void handleClearCookie()}
              disabled={settingsBusy || !integration?.has_cookie_values}
              style={{ width: "100%", justifyContent: "center" }}
            >
              <span className="icon icon-sm">delete_sweep</span>
              清除登录态
            </button>

            {settingsLoading && <p className="text-meta" style={{ marginTop: 12 }}>正在读取 B站授权…</p>}
            {settingsMessage && <div className="feedback feedback-success" style={{ marginTop: 12 }}>{settingsMessage}</div>}
            {settingsError && <div className="feedback feedback-error" style={{ marginTop: 12 }}>{settingsError}</div>}
          </div>
        </div>

        <div className="card bilibili-preview-card">
          <div className="card-header bilibili-preview-header">
            <span className="card-title">视频预览</span>
            <span className={`chip ${preview ? "chip-success" : "chip-neutral"}`}>{preview ? "待确认" : "未解析"}</span>
          </div>

          {preview ? (
            <div className="bilibili-preview-content">
              {preview.cover_url ? (
                <img className="bilibili-preview-cover" src={bilibiliCoverSrc(apiBaseUrl, preview.cover_url)} alt="" />
              ) : (
                <div className="bilibili-preview-cover bilibili-preview-cover-empty">
                  <span className="icon">smart_display</span>
                </div>
              )}

              <div className="bilibili-preview-main">
                <h3>{preview.title}</h3>
                <div className="bilibili-preview-meta">
                  {preview.owner_name && <span>UP {preview.owner_name}</span>}
                  {preview.duration_text && <span>时长 {preview.duration_text}</span>}
                  {preview.bvid && <span>{preview.bvid}</span>}
                </div>
                {preview.description && <p>{preview.description}</p>}
              </div>

              <div className="bilibili-preview-facts">
                {[
                  { label: "UP 主", value: preview.owner_name ?? "未知" },
                  { label: "时长", value: preview.duration_text ?? "未知" },
                  {
                    label: "分集",
                    value:
                      preview.page_count && preview.page_count > 1
                        ? `${preview.page_count} 个分 P`
                        : "单个视频",
                  },
                ].map((row) => (
                  <div key={row.label}>
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))}
              </div>

              <button
                className="btn btn-bili-primary"
                type="button"
                disabled={confirmBusy}
                onClick={() => void handleConfirmImport()}
              >
                <span className="icon icon-sm">{confirmBusy ? "sync" : "playlist_add_check"}</span>
                {confirmBusy ? "加入中…" : "确认加入稍后阅读"}
              </button>

              {importResult && (
                <div className="feedback feedback-success">
                  <div style={{ fontWeight: 700, marginBottom: 6 }}>
                    {importResult.is_duplicate ? "链接已存在" : "已加入稍后阅读"}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <span className="chip chip-success">UID {importResult.uid}</span>
                    <span className="chip chip-success">状态 {importResult.status}</span>
                    <span className="chip chip-success">位置 {displayFolderName(importResult.folder_name, importResult.folder_id === "inbox")}</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bilibili-preview-empty">
              <span className="icon icon-lg">movie_info</span>
              <p>这里会显示封面、标题、UP 主和时长。确认是正确视频后，再加入稍后阅读并启动字幕、转写和 AI 摘要。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
