import { useEffect } from "react";
import { useAppState } from "../state/appState";

const themeOptions = [
  { value: "system", label: "跟随系统", icon: "brightness_auto" },
  { value: "light",  label: "浅色",    icon: "light_mode" },
  { value: "dark",   label: "深色",    icon: "dark_mode" },
] as const;

function providerTypeLabel(t: string) {
  switch (t) {
    case "doubao": return "豆包";
    case "openai_compatible": return "OpenAI 兼容";
    case "custom": return "自定义";
    default: return "其他";
  }
}

export function SettingsPage() {
  const { apiBaseUrl, folders, lastError, loadFolders, loadProviders, providers, resolvedTheme, themeMode, setThemeMode, workspace } = useAppState();

  useEffect(() => {
    if (!providers.length) void loadProviders();
    if (!folders.length) void loadFolders();
  }, [folders.length, loadFolders, loadProviders, providers.length]);

  return (
    <div className="page">
      {/* Header */}
      <div className="page-header">
        <p className="page-eyebrow">设置</p>
        <h2 className="page-title">系统配置</h2>
        <p className="page-lead">主题外观、工作区信息、模型服务与文件夹管理。</p>
      </div>

      <div className="stack-lg" style={{ maxWidth: 760 }}>
        {/* Appearance */}
        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>palette</span>
            外观
          </div>
          <div className="tab-row" style={{ alignSelf: "flex-start" }}>
            {themeOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`tab ${themeMode === opt.value ? "active" : ""}`}
                onClick={() => setThemeMode(opt.value)}
                style={{ display: "flex", alignItems: "center", gap: 6 }}
              >
                <span className="icon icon-sm">{opt.icon}</span>
                {opt.label}
              </button>
            ))}
          </div>
          <p className="text-meta">当前：{resolvedTheme === "dark" ? "深色模式" : "浅色模式"}。界面语言固定为中文。</p>
        </div>

        {/* Workspace */}
        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>workspaces</span>
            工作区
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {[
              { label: "工作区名称", value: workspace?.workspace_name ?? "OneRadar", icon: "badge" },
              { label: "服务端地址", value: apiBaseUrl, icon: "dns" },
              { label: "界面语言", value: "中文", icon: "translate" },
              { label: "单用户模式", value: workspace?.single_user_mode ? "是" : "—", icon: "person" },
            ].map((item) => (
              <div key={item.label} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 14px", background: "var(--surface-container)", borderRadius: "var(--radius-sm)" }}>
                <span className="icon" style={{ color: "var(--outline)", marginTop: 1 }}>{item.icon}</span>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--outline)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>{item.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--on-surface)", wordBreak: "break-all" }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
          {lastError && <div className="feedback feedback-error">{lastError}</div>}
        </div>

        {/* Folders */}
        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>folder</span>
            文件夹 <span style={{ fontWeight: 400, color: "var(--outline)", fontSize: 13 }}>（{folders.length} 个）</span>
          </div>
          <div className="stack-sm">
            {folders.map((f) => (
              <div key={f.id} className="provider-row">
                <div className="provider-icon">
                  <span className="icon icon-sm">{f.is_builtin ? "inbox" : "folder"}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--on-surface)" }}>{f.name}</div>
                  <div style={{ fontSize: 12, color: "var(--outline)" }}>{f.is_builtin ? "内置文件夹" : "自定义文件夹"}</div>
                </div>
                <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                  <span className="chip chip-neutral">{f.item_count} 条</span>
                  <span className="chip chip-neutral" style={{ fontFamily: "monospace", fontSize: 10 }}>{f.id}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Model providers */}
        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>smart_toy</span>
            模型服务 <span style={{ fontWeight: 400, color: "var(--outline)", fontSize: 13 }}>（{providers.length} 个）</span>
          </div>
          {providers.length ? (
            <div className="stack-sm">
              {providers.map((p) => (
                <div key={p.id} className="provider-row">
                  <div className="provider-icon" style={{ background: p.is_enabled ? "rgba(70,83,195,0.1)" : "var(--surface-high)" }}>
                    <span className="icon icon-sm" style={{ color: p.is_enabled ? "var(--primary)" : "var(--outline)" }}>
                      {p.is_enabled ? "psychology" : "psychology_alt"}
                    </span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, color: "var(--on-surface)" }}>{p.provider_name}</div>
                    <div style={{ fontSize: 12, color: "var(--outline)" }}>{providerTypeLabel(p.provider_type)} · {p.base_url ?? "地址未配置"}</div>
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", flexShrink: 0, justifyContent: "flex-end" }}>
                    <span className={`chip ${p.is_enabled ? "chip-success" : "chip-neutral"}`}>{p.is_enabled ? "启用" : "停用"}</span>
                    {p.chat_model && <span className="chip chip-neutral" style={{ fontSize: 10 }}>对话 {p.chat_model}</span>}
                    {p.transcription_model && <span className="chip chip-neutral" style={{ fontSize: 10 }}>转写 {p.transcription_model}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state" style={{ padding: "24px 0" }}>
              <div className="empty-state-icon"><span className="icon icon-lg">smart_toy</span></div>
              <h3>暂无模型服务</h3>
              <p>请先完成服务端连接以读取模型配置。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
