import { useEffect, useMemo, useState } from "react";
import { createApiClient } from "../api";
import type { ApiBilibiliIntegrationSettings, ApiProvider } from "../api";
import { useAppState } from "../state/appState";
import { displayFolderName } from "../utils/display";

const DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";
const DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1";

const themeOptions = [
  { value: "system", label: "跟随系统", icon: "brightness_auto" },
  { value: "light", label: "浅色", icon: "light_mode" },
  { value: "dark", label: "深色", icon: "dark_mode" },
] as const;

type ProviderKind = "doubao" | "openai_compatible" | "deepseek" | "custom";
type ProviderCapability = "llm" | "asr";
type ThinkingMode = "default" | "enabled" | "disabled";

type ProviderFormState = {
  id: string | null;
  capability: ProviderCapability;
  provider_name: string;
  provider_type: ProviderKind;
  base_url: string;
  api_key: string;
  chat_model: string;
  transcription_model: string;
  transcription_app_id: string;
  transcription_access_token: string;
  transcription_secret_key: string;
  thinking_mode: ThinkingMode;
  is_enabled: boolean;
};

function providerTypeLabel(t: string) {
  switch (t) {
    case "doubao": return "豆包";
    case "deepseek": return "DeepSeek";
    case "openai_compatible": return "OpenAI 兼容";
    case "custom": return "自定义";
    default: return "其他";
  }
}

function connectionLabel(state: "idle" | "checking" | "connected" | "unavailable") {
  switch (state) {
    case "checking": return "连接中";
    case "connected": return "服务端在线";
    case "unavailable": return "服务端不可用";
    default: return "等待连接";
  }
}

function capabilityOf(provider: ApiProvider): ProviderCapability {
  if (provider.capability === "asr" || provider.capability === "llm") return provider.capability;
  if ((provider.transcription_model || provider.transcription_app_id) && !provider.chat_model) return "asr";
  return "llm";
}

function emptyProviderForm(capability: ProviderCapability): ProviderFormState {
  return {
    id: null,
    capability,
    provider_name: capability === "llm" ? "Doubao LLM" : "Doubao ASR",
    provider_type: "doubao",
    base_url: capability === "llm" ? DOUBAO_BASE_URL : "",
    api_key: "",
    chat_model: "",
    transcription_model: capability === "asr" ? "volc.bigasr.auc_turbo" : "",
    transcription_app_id: "",
    transcription_access_token: "",
    transcription_secret_key: "",
    thinking_mode: "default",
    is_enabled: true,
  };
}

function providerToForm(provider: ApiProvider): ProviderFormState {
  const capability = capabilityOf(provider);
  return {
    id: provider.id,
    capability,
    provider_name: provider.provider_name,
    provider_type: (provider.provider_type as ProviderKind | undefined) ?? "custom",
    base_url: provider.base_url ?? "",
    api_key: "",
    chat_model: provider.chat_model ?? "",
    transcription_model: provider.transcription_model ?? "",
    transcription_app_id: provider.transcription_app_id ?? "",
    transcription_access_token: "",
    transcription_secret_key: "",
    thinking_mode: provider.thinking_mode === "enabled" || provider.thinking_mode === "disabled" ? provider.thinking_mode : "default",
    is_enabled: provider.is_enabled,
  };
}

function applyProviderDefaults(form: ProviderFormState, providerType: ProviderKind): ProviderFormState {
  if (providerType === "deepseek") {
    return {
      ...form,
      provider_type: "deepseek",
      provider_name:
        form.provider_name && !["Doubao", "Doubao LLM", "DeepSeek", "DeepSeek LLM"].includes(form.provider_name)
          ? form.provider_name
          : "DeepSeek LLM",
      base_url: form.capability === "llm" && (!form.base_url || form.base_url === DOUBAO_BASE_URL) ? DEEPSEEK_BASE_URL : form.base_url,
      chat_model: form.capability === "llm" ? form.chat_model : "",
      transcription_model: "",
      thinking_mode: form.thinking_mode,
    };
  }
  if (providerType !== "doubao") {
    return {
      ...form,
      provider_type: providerType,
      base_url: form.capability === "llm" ? form.base_url : "",
      chat_model: form.capability === "llm" ? form.chat_model : "",
      transcription_model: form.capability === "asr" ? form.transcription_model : "",
      thinking_mode: form.thinking_mode,
    };
  }
  return {
    ...form,
    provider_type: "doubao",
    provider_name:
      form.provider_name && !["Doubao", "Doubao LLM", "Doubao ASR"].includes(form.provider_name)
        ? form.provider_name
        : form.capability === "llm" ? "Doubao LLM" : "Doubao ASR",
    base_url: form.capability === "llm" && (!form.base_url || form.base_url === DEEPSEEK_BASE_URL) ? DOUBAO_BASE_URL : form.base_url,
    chat_model: form.capability === "llm" ? form.chat_model : "",
    transcription_model: form.capability === "asr" ? (form.transcription_model || "volc.bigasr.auc_turbo") : "",
  };
}

function providerCredentialConfigured(provider: ApiProvider | undefined, capability: ProviderCapability, field: "api_key" | "access_token" | "secret_key") {
  if (!provider) return false;
  if (capability === "llm" && field === "api_key") return Boolean(provider.api_key_configured);
  if (capability === "asr" && field === "access_token") return Boolean(provider.transcription_access_token_configured);
  if (capability === "asr" && field === "secret_key") return Boolean(provider.transcription_secret_key_configured);
  return false;
}

function thinkingModeLabel(mode: string | undefined) {
  switch (mode) {
    case "enabled": return "思考：开启";
    case "disabled": return "思考：关闭";
    default: return "思考：默认";
  }
}

function showAppToast(message: string, tone: "success" | "error" | "info" = "info") {
  window.dispatchEvent(new CustomEvent("oneradar:toast", { detail: { message, tone } }));
}

export function SettingsPage() {
  const { apiBaseUrl, connectionState, folders, lastError, loadFolders, loadProviders, providers, resolvedTheme, themeMode, setThemeMode, workspace } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [bilibiliIntegration, setBilibiliIntegration] = useState<ApiBilibiliIntegrationSettings | null>(null);
  const [integrationLoading, setIntegrationLoading] = useState(true);
  const [integrationSaving, setIntegrationSaving] = useState(false);
  const [integrationMessage, setIntegrationMessage] = useState<string | null>(null);
  const [integrationError, setIntegrationError] = useState<string | null>(null);
  const [llmForm, setLlmForm] = useState<ProviderFormState>(() => emptyProviderForm("llm"));
  const [asrForm, setAsrForm] = useState<ProviderFormState>(() => emptyProviderForm("asr"));
  const [editing, setEditing] = useState<ProviderCapability | null>(null);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerTestingId, setProviderTestingId] = useState<string | null>(null);

  const llmProviders = providers.filter((provider) => capabilityOf(provider) === "llm");
  const asrProviders = providers.filter((provider) => capabilityOf(provider) === "asr");

  useEffect(() => {
    if (!providers.length) void loadProviders();
    if (!folders.length) void loadFolders();
  }, [folders.length, loadFolders, loadProviders, providers.length]);

  useEffect(() => {
    let cancelled = false;
    async function loadIntegration() {
      setIntegrationLoading(true);
      setIntegrationError(null);
      try {
        const result = await client.getBilibiliIntegration();
        if (!cancelled) setBilibiliIntegration(result);
      } catch (e) {
        if (!cancelled) setIntegrationError(e instanceof Error ? e.message : "读取视频增强设置失败");
      } finally {
        if (!cancelled) setIntegrationLoading(false);
      }
    }
    void loadIntegration();
    return () => {
      cancelled = true;
    };
  }, [client]);

  async function handleVisualEnhancementChange(enabled: boolean) {
    setIntegrationSaving(true);
    setIntegrationMessage(null);
    setIntegrationError(null);
    try {
      const result = await client.updateBilibiliIntegration({
        is_enabled: Boolean(bilibiliIntegration?.is_enabled),
        visual_enhancement_enabled: enabled,
      });
      setBilibiliIntegration(result);
      setIntegrationMessage(enabled ? "已开启多模态视觉增强。" : "已关闭多模态视觉增强。");
    } catch (e) {
      setIntegrationError(e instanceof Error ? e.message : "保存视频增强设置失败");
    } finally {
      setIntegrationSaving(false);
    }
  }

  async function saveProvider(form: ProviderFormState) {
    const existingProvider = providers.find((provider) => provider.id === form.id);
    const name = form.provider_name.trim() || (form.capability === "llm" ? "大语言模型" : "转写模型");
    const baseUrl = form.base_url.trim();
    const apiKey = form.api_key.trim();
    const chatModel = form.chat_model.trim();
    const transcriptionAppId = form.transcription_app_id.trim();
    const transcriptionModel = form.transcription_model.trim();
    const transcriptionAccessToken = form.transcription_access_token.trim();
    const transcriptionSecretKey = form.transcription_secret_key.trim();

    if (form.capability === "llm") {
      if (!baseUrl) {
        setProviderError("大语言模型需要填写 BaseURL。");
        return;
      }
      if (!chatModel) {
        setProviderError("大语言模型需要填写模型名或 Endpoint。");
        return;
      }
      if (!apiKey && !providerCredentialConfigured(existingProvider, "llm", "api_key")) {
        setProviderError("大语言模型需要填写 API Key。");
        return;
      }
    } else {
      if (!transcriptionAppId) {
        setProviderError("ASR 模型需要填写 APP ID。");
        return;
      }
      if (!transcriptionModel) {
        setProviderError("ASR 模型需要填写资源 ID。");
        return;
      }
      if (!transcriptionAccessToken && !providerCredentialConfigured(existingProvider, "asr", "access_token")) {
        setProviderError("ASR 模型需要填写 Access Token。");
        return;
      }
      if (!transcriptionSecretKey && !providerCredentialConfigured(existingProvider, "asr", "secret_key")) {
        setProviderError("ASR 模型需要填写 Secret Key。");
        return;
      }
    }

    setProviderSaving(true);
    setProviderError(null);
    try {
      const payload = {
        provider_name: name,
        provider_type: form.provider_type,
        capability: form.capability,
        base_url: form.capability === "llm" ? baseUrl : null,
        api_key: form.capability === "llm" ? apiKey || null : null,
        chat_model: form.capability === "llm" ? chatModel : null,
        embedding_model: null,
        transcription_model: form.capability === "asr" ? transcriptionModel : null,
        transcription_app_id: form.capability === "asr" ? transcriptionAppId : null,
        transcription_access_token: form.capability === "asr" ? transcriptionAccessToken || null : null,
        transcription_secret_key: form.capability === "asr" ? transcriptionSecretKey || null : null,
        thinking_mode: form.capability === "llm" ? form.thinking_mode : null,
        is_enabled: true,
      };
      await (form.id ? client.updateProvider(form.id, payload) : client.createProvider(payload));
      await loadProviders();
      setEditing(null);
      setLlmForm(emptyProviderForm("llm"));
      setAsrForm(emptyProviderForm("asr"));
      showAppToast(form.capability === "llm" ? "大语言模型已保存并设为当前使用。" : "转写模型已保存并设为当前使用。", "success");
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "保存模型失败");
    } finally {
      setProviderSaving(false);
    }
  }

  async function deleteProvider(providerId: string) {
    setProviderSaving(true);
    setProviderError(null);
    try {
      await client.deleteProvider(providerId);
      await loadProviders();
      showAppToast("模型配置已删除。", "success");
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "删除模型失败");
    } finally {
      setProviderSaving(false);
    }
  }

  async function activateProvider(provider: ApiProvider) {
    const capability = capabilityOf(provider);
    setProviderSaving(true);
    setProviderError(null);
    try {
      await client.updateProvider(provider.id, {
        provider_name: provider.provider_name,
        provider_type: provider.provider_type as ProviderKind,
        capability,
        base_url: capability === "llm" ? provider.base_url ?? null : null,
        api_key: null,
        chat_model: capability === "llm" ? provider.chat_model ?? null : null,
        embedding_model: null,
        transcription_model: capability === "asr" ? provider.transcription_model ?? null : null,
        transcription_app_id: capability === "asr" ? provider.transcription_app_id ?? null : null,
        transcription_access_token: null,
        transcription_secret_key: null,
        thinking_mode: capability === "llm" ? provider.thinking_mode ?? "default" : null,
        is_enabled: true,
      });
      await loadProviders();
      showAppToast(capability === "llm" ? "已切换当前大语言模型。" : "已切换当前转写模型。", "success");
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "切换当前模型失败");
    } finally {
      setProviderSaving(false);
    }
  }

  async function testProvider(provider: ApiProvider) {
    setProviderTestingId(provider.id);
    setProviderError(null);
    try {
      const result = await client.testProvider(provider.id);
      await loadProviders();
      if (result.ok) {
        showAppToast(result.message || `模型测试通过，耗时 ${result.latency_ms} ms。`, "success");
      } else {
        setProviderError(result.message || "模型测试失败。");
        showAppToast(result.message || "模型测试失败。", "error");
      }
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "模型测试失败");
    } finally {
      setProviderTestingId(null);
    }
  }

  function providerRow(provider: ApiProvider) {
    const capability = capabilityOf(provider);
    const isAsr = capability === "asr";
    return (
      <div key={provider.id} className="provider-row">
        <div className="provider-icon" style={{ background: provider.is_enabled ? "rgba(var(--primary-rgb),0.1)" : "var(--surface-high)" }}>
          <span className="icon icon-sm" style={{ color: provider.is_enabled ? "var(--primary)" : "var(--outline)" }}>
            {isAsr ? "graphic_eq" : "psychology"}
          </span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: "var(--on-surface)" }}>{provider.provider_name}</div>
          <div style={{ fontSize: 12, color: "var(--outline)" }}>
            {providerTypeLabel(provider.provider_type)} · {isAsr ? provider.transcription_app_id ?? "APP ID 未配置" : provider.base_url ?? "BaseURL 未配置"}
          </div>
          {!isAsr && <div style={{ fontSize: 12, color: "var(--outline)", marginTop: 2 }}>{thinkingModeLabel(provider.thinking_mode)}</div>}
        </div>
        <div className="provider-row-actions">
          {provider.is_enabled ? (
            <span className="chip chip-success provider-row-current">当前使用</span>
          ) : (
            <button type="button" className="btn btn-ghost btn-sm provider-row-activate" onClick={() => void activateProvider(provider)} disabled={providerSaving}>
              设为当前使用
            </button>
          )}
          {!isAsr ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void testProvider(provider)} disabled={providerTestingId === provider.id || providerSaving}>
              {providerTestingId === provider.id ? "测试中" : "测试"}
            </button>
          ) : (
            <span aria-hidden="true" />
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              const form = providerToForm(provider);
              if (capability === "llm") setLlmForm(form);
              else setAsrForm(form);
              setEditing(capability);
              setProviderError(null);
            }}
          >
            编辑
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void deleteProvider(provider.id)} disabled={providerSaving}>
            删除
          </button>
        </div>
      </div>
    );
  }

  function providerEditor(form: ProviderFormState, setForm: (updater: (current: ProviderFormState) => ProviderFormState) => void) {
    const isAsr = form.capability === "asr";
    return (
      <div className="provider-editor">
        <div className="provider-editor-header">
          <div>
            <div className="rail-section-title">{form.id ? "编辑模型配置" : "添加模型配置"}</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(null)}>
            收起
          </button>
        </div>
        <label>
          <span className="text-caption">供应商</span>
          <select
            className="input"
            value={form.provider_type}
            onChange={(event) => setForm((current) => applyProviderDefaults(current, event.target.value as ProviderKind))}
          >
            <option value="doubao">豆包</option>
            <option value="deepseek" disabled={isAsr}>DeepSeek</option>
            <option value="openai_compatible" disabled={isAsr}>OpenAI 兼容</option>
            <option value="custom" disabled={isAsr}>自定义</option>
          </select>
        </label>
        <label>
          <span className="text-caption">自定义名称</span>
          <input
            className="input"
            value={form.provider_name}
            onChange={(event) => setForm((current) => ({ ...current, provider_name: event.target.value }))}
          />
        </label>
        {!isAsr && (
          <>
            <label>
              <span className="text-caption">BaseURL</span>
              <input
                className="input"
                value={form.base_url}
                onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                placeholder={form.provider_type === "doubao" ? DOUBAO_BASE_URL : form.provider_type === "deepseek" ? DEEPSEEK_BASE_URL : "https://example.com/v1"}
              />
            </label>
            <label>
              <span className="text-caption">API Key</span>
              <input
                className="input"
                type="password"
                value={form.api_key}
                onChange={(event) => setForm((current) => ({ ...current, api_key: event.target.value }))}
                placeholder={providers.find((provider) => provider.id === form.id)?.api_key_configured ? "已保存，留空沿用；填写新值可覆盖" : "填入 API Key"}
              />
            </label>
            <label>
              <span className="text-caption">模型名 / Endpoint</span>
              <input
                className="input"
                value={form.chat_model}
                onChange={(event) => setForm((current) => ({ ...current, chat_model: event.target.value }))}
                placeholder={form.provider_type === "doubao" ? "填入你自己的 Endpoint，例如 ep-..." : form.provider_type === "deepseek" ? "deepseek-chat" : "模型名"}
              />
            </label>
            <label>
              <span className="text-caption">思考模式</span>
              <div className="tab-row" style={{ alignSelf: "flex-start" }}>
                {(["default", "enabled", "disabled"] as ThinkingMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={`tab ${form.thinking_mode === mode ? "active" : ""}`}
                    onClick={() => setForm((current) => ({ ...current, thinking_mode: mode }))}
                  >
                    {mode === "default" ? "默认" : mode === "enabled" ? "开启" : "关闭"}
                  </button>
                ))}
              </div>
            </label>
          </>
        )}
        {isAsr && form.provider_type === "doubao" && (
          <>
            <label>
              <span className="text-caption">APP ID</span>
              <input
                className="input"
                value={form.transcription_app_id}
                onChange={(event) => setForm((current) => ({ ...current, transcription_app_id: event.target.value }))}
                placeholder="填入豆包语音 APP ID"
              />
            </label>
            <label>
              <span className="text-caption">Access Token</span>
              <input
                className="input"
                type="password"
                value={form.transcription_access_token}
                onChange={(event) => setForm((current) => ({ ...current, transcription_access_token: event.target.value }))}
                placeholder={providers.find((provider) => provider.id === form.id)?.transcription_access_token_configured ? "已保存，留空沿用；填写新值可覆盖" : "填入 Access Token"}
              />
            </label>
            <label>
              <span className="text-caption">Secret Key</span>
              <input
                className="input"
                type="password"
                value={form.transcription_secret_key}
                onChange={(event) => setForm((current) => ({ ...current, transcription_secret_key: event.target.value }))}
                placeholder={providers.find((provider) => provider.id === form.id)?.transcription_secret_key_configured ? "已保存，留空沿用；填写新值可覆盖" : "填入 Secret Key"}
              />
            </label>
            <label>
              <span className="text-caption">资源 ID</span>
              <input
                className="input"
                value={form.transcription_model}
                onChange={(event) => setForm((current) => ({ ...current, transcription_model: event.target.value }))}
                placeholder="volc.bigasr.auc_turbo"
              />
            </label>
          </>
        )}
        <div className="btn-group">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => void saveProvider(form)} disabled={providerSaving}>
            <span className="icon icon-sm">{form.id ? "save" : "add"}</span>
            {form.id ? "保存修改" : "添加"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <p className="page-eyebrow">设置</p>
        <h2 className="page-title">系统配置</h2>
        <p className="page-lead">主题外观、工作区信息、模型服务与知识库管理。</p>
      </div>

      <div className="stack-lg" style={{ maxWidth: 820 }}>
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

        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>workspaces</span>
            工作区
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {[
              { label: "工作区名称", value: workspace?.workspace_name ?? "OneRadar", icon: "badge" },
              { label: "服务端状态", value: connectionLabel(connectionState), icon: "cloud_done", status: connectionState },
              { label: "服务端地址", value: apiBaseUrl, icon: "dns" },
              { label: "界面语言", value: "中文", icon: "translate" },
              { label: "单用户模式", value: workspace?.single_user_mode ? "是" : "—", icon: "person" },
            ].map((item) => (
              <div key={item.label} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 14px", background: "var(--surface-container)", borderRadius: "var(--radius-sm)" }}>
                {item.status ? (
                  <span className={`status-dot status-${item.status}`} style={{ marginTop: 7 }} />
                ) : (
                  <span className="icon" style={{ color: "var(--outline)", marginTop: 1 }}>{item.icon}</span>
                )}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--outline)", textTransform: "uppercase", marginBottom: 4 }}>{item.label}</div>
                  <div style={{ fontSize: 14, fontWeight: 500, color: "var(--on-surface)", wordBreak: "break-all" }}>{item.value}</div>
                </div>
              </div>
            ))}
          </div>
          {lastError && <div className="feedback feedback-error">{lastError}</div>}
        </div>

        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>smart_toy</span>
            模型服务
          </div>

          <div className="settings-model-block">
            <div className="settings-model-block-header">
              <div>
                <h3>大语言模型</h3>
                <p>用于摘要、问答、视频视觉增强等文本理解任务。</p>
              </div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setLlmForm(emptyProviderForm("llm")); setEditing("llm"); }}>
                <span className="icon icon-sm">add</span>
                添加模型服务
              </button>
            </div>
            <div className="stack-sm">
              {llmProviders.length ? llmProviders.map(providerRow) : <p className="text-meta">还没有配置大语言模型。</p>}
            </div>
            {editing === "llm" && providerEditor(llmForm, setLlmForm)}
          </div>

          <div className="settings-model-block">
            <div className="settings-model-block-header">
              <div>
                <h3>转写模型（ASR）</h3>
                <p>用于播客音频和无字幕视频的语音转文字。</p>
              </div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setAsrForm(emptyProviderForm("asr")); setEditing("asr"); }}>
                <span className="icon icon-sm">add</span>
                添加模型服务
              </button>
            </div>
            <div className="stack-sm">
              {asrProviders.length ? asrProviders.map(providerRow) : <p className="text-meta">还没有配置转写模型。</p>}
            </div>
            {editing === "asr" && providerEditor(asrForm, setAsrForm)}
          </div>

          {providerError && (
            <div className="stack-sm">
              <div className="feedback feedback-error">{providerError}</div>
            </div>
          )}

          <div className="settings-subsection">
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={Boolean(bilibiliIntegration?.visual_enhancement_enabled)}
                disabled={integrationLoading || integrationSaving}
                onChange={(e) => void handleVisualEnhancementChange(e.target.checked)}
              />
              <span>启用视频多模态视觉增强</span>
            </label>
            <p className="text-caption visual-enhancement-note">
              开启后，B站视频仍优先使用字幕，没有字幕再走音频转写；在已有文本基础上额外调用支持视频/图像的大模型分析画面。
            </p>
            {integrationLoading && <p className="text-meta">正在读取视频增强设置…</p>}
            {integrationMessage && <div className="feedback feedback-success">{integrationMessage}</div>}
            {integrationError && <div className="feedback feedback-error">{integrationError}</div>}
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>folder</span>
            知识库 <span style={{ fontWeight: 400, color: "var(--outline)", fontSize: 13 }}>（{folders.length} 个）</span>
          </div>
          <div className="stack-sm">
            {folders.map((f) => (
              <div key={f.id} className="provider-row">
                <div className="provider-icon">
                  <span className="icon icon-sm">{f.is_builtin ? "inbox" : "folder"}</span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--on-surface)" }}>{displayFolderName(f.name, f.is_builtin)}</div>
                  <div style={{ fontSize: 12, color: "var(--outline)" }}>{f.is_builtin ? "内置入口" : "收藏夹"}</div>
                </div>
                <span className="chip chip-neutral">{f.item_count} 条</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
