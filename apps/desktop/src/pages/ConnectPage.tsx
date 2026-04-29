import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAppState } from "../state/appState";
import { displayFolderName } from "../utils/display";

function connectionStateLabel(state: "idle" | "checking" | "connected" | "unavailable") {
  switch (state) {
    case "connected": return "已连接";
    case "checking": return "检测中";
    case "unavailable": return "不可用";
    default: return "待连接";
  }
}

function connectionStateChip(state: "idle" | "checking" | "connected" | "unavailable") {
  switch (state) {
    case "connected": return "chip chip-success";
    case "checking": return "chip chip-primary";
    case "unavailable": return "chip chip-error";
    default: return "chip chip-neutral";
  }
}

function providerTypeLabel(t: string) {
  switch (t) {
    case "doubao": return "豆包";
    case "openai_compatible": return "OpenAI 兼容";
    case "custom": return "自定义";
    default: return "其他";
  }
}

export function ConnectPage() {
  const { apiBaseUrl, connectionState, health, lastError, loadWorkspace, refreshConnection, workspace, folders, providers, themeMode, resolvedTheme } = useAppState();
  const [serverUrl, setServerUrl] = useState(apiBaseUrl);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => { setServerUrl(apiBaseUrl); }, [apiBaseUrl]);

  const inboxFolder = useMemo(
    () => workspace?.default_inbox_folder ?? folders.find((f) => f.id === "inbox"),
    [folders, workspace]
  );

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true); setMessage(null);
    try { await refreshConnection(serverUrl); setMessage("地址已保存，连接检测完成。"); }
    finally { setBusy(false); }
  }

  async function handleCheck() {
    setBusy(true); setMessage(null);
    try { await refreshConnection(serverUrl); setMessage("连接已更新。"); }
    finally { setBusy(false); }
  }

  async function handleReload() {
    setBusy(true); setMessage(null);
    try { await loadWorkspace(); setMessage("已重新同步服务端配置。"); }
    finally { setBusy(false); }
  }

  return (
    <div className="page" style={{ display: "flex", alignItems: "flex-start", justifyContent: "center", minHeight: "calc(100vh - 60px)" }}>
      <div style={{ width: "100%", maxWidth: 560, paddingTop: 40 }}>
        {/* Brand header */}
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <div style={{
            width: 64, height: 64, borderRadius: 18,
            background: "linear-gradient(135deg, var(--primary), var(--primary-container))",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 20px",
            boxShadow: "0 8px 24px rgba(var(--primary-rgb),0.18)"
          }}>
            <span className="icon icon-lg" style={{ fontSize: 32, color: "var(--on-primary)" }}>radar</span>
          </div>
          <h1 style={{ fontFamily: "Manrope, sans-serif", fontSize: "1.75rem", fontWeight: 700, letterSpacing: "-0.03em", margin: "0 0 8px" }}>
            连接服务端
          </h1>
          <p className="text-meta">配置 OneRadar API 服务地址以开始使用</p>
        </div>

        {/* Connection card */}
        <div className="card" style={{ marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
            <h2 style={{ fontFamily: "Manrope, sans-serif", fontSize: 16, fontWeight: 700, margin: 0 }}>服务端地址</h2>
            <span className={connectionStateChip(connectionState)}>
              <span className="icon icon-sm">{connectionState === "connected" ? "check_circle" : connectionState === "checking" ? "sync" : "radio_button_unchecked"}</span>
              {connectionStateLabel(connectionState)}
            </span>
          </div>

          <form className="stack" onSubmit={(e) => void handleSubmit(e)}>
            <div className="field">
              <label htmlFor="server-url">API 地址</label>
              <input
                id="server-url"
                className="input"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                placeholder="http://127.0.0.1:8000"
              />
            </div>
            <div className="btn-group">
              <button className="btn btn-primary" type="submit" disabled={busy} style={{ flex: 1, justifyContent: "center" }}>
                <span className="icon icon-sm">{busy ? "sync" : "link"}</span>
                {busy ? "检测中…" : "保存并检测"}
              </button>
              <button className="btn btn-ghost" type="button" onClick={() => void handleCheck()} disabled={busy}>
                <span className="icon icon-sm">wifi_find</span>
                仅检测
              </button>
              <button className="btn btn-ghost" type="button" onClick={() => void handleReload()} disabled={busy}>
                <span className="icon icon-sm">refresh</span>
                重新同步
              </button>
            </div>
          </form>

          {message && <div className="feedback feedback-success" style={{ marginTop: 16 }}>{message}</div>}
          {lastError && <div className="feedback feedback-error" style={{ marginTop: 16 }}>{lastError}</div>}

          {/* Quick info */}
          <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {[
              { label: "服务版本", value: health?.version ?? "未读取", icon: "tag" },
              { label: "工作区", value: workspace?.workspace_name ?? "未读取", icon: "workspaces" },
              { label: "默认入口", value: displayFolderName(inboxFolder?.name, true), icon: "inbox" },
              { label: "主题", value: themeMode === "system" ? `系统 (${resolvedTheme === "dark" ? "深色" : "浅色"})` : (themeMode === "dark" ? "深色" : "浅色"), icon: "palette" },
            ].map((item) => (
              <div key={item.label} style={{ padding: "10px 12px", background: "var(--surface-container)", borderRadius: "var(--radius-sm)", display: "flex", gap: 10, alignItems: "center" }}>
                <span className="icon icon-sm" style={{ color: "var(--outline)" }}>{item.icon}</span>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--outline)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{item.label}</div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--on-surface)" }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Model providers */}
        {providers.length > 0 && (
          <div className="card">
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--on-surface-v)", marginBottom: 14, display: "flex", alignItems: "center", gap: 6 }}>
              <span className="icon icon-sm" style={{ color: "var(--tertiary)" }}>smart_toy</span>
              已加载 {providers.length} 个模型服务
            </div>
            <div className="stack-sm">
              {providers.map((p) => (
                <div key={p.id} className="provider-row">
                  <div className="provider-icon" style={{ background: p.is_enabled ? "rgba(var(--primary-rgb),0.1)" : "var(--surface-high)" }}>
                    <span className="icon icon-sm" style={{ color: p.is_enabled ? "var(--primary)" : "var(--outline)" }}>psychology</span>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{p.provider_name}</div>
                    <div style={{ fontSize: 12, color: "var(--outline)" }}>{providerTypeLabel(p.provider_type)}</div>
                  </div>
                  <span className={`chip ${p.is_enabled ? "chip-success" : "chip-neutral"}`}>{p.is_enabled ? "启用" : "停用"}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
