import { useEffect, useMemo, useState } from "react";
import { createApiClient } from "../api";
import type { ApiIntegrationToken, ApiProvider } from "../api";
import { useAppState } from "../state/appState";

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
type ModelInputCapability = "text" | "image" | "audio" | "video";

const modelInputCapabilityOptions: Array<{ value: ModelInputCapability; label: string }> = [
  { value: "text", label: "文字" },
  { value: "image", label: "图片" },
  { value: "audio", label: "音频" },
  { value: "video", label: "视频" },
];

type ProviderFormState = {
  id: string | null;
  capability: ProviderCapability;
  input_capabilities: ModelInputCapability[];
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

function capabilityOf(provider: ApiProvider): ProviderCapability {
  if (provider.capability === "asr" || provider.capability === "llm") return provider.capability;
  if ((provider.transcription_model || provider.transcription_app_id) && !provider.chat_model) return "asr";
  return "llm";
}

function defaultInputCapabilities(capability: ProviderCapability): ModelInputCapability[] {
  return capability === "asr" ? ["audio"] : ["text"];
}

function normalizeInputCapabilities(value: Array<string> | undefined, capability: ProviderCapability): ModelInputCapability[] {
  const selected = new Set(value?.filter((item): item is ModelInputCapability => (
    item === "text" || item === "image" || item === "audio" || item === "video"
  )));
  const normalized = modelInputCapabilityOptions
    .map((option) => option.value)
    .filter((value) => selected.has(value));
  return normalized.length ? normalized : defaultInputCapabilities(capability);
}

function inputCapabilityLabels(value: Array<string> | undefined, capability: ProviderCapability) {
  const normalized = normalizeInputCapabilities(value, capability);
  return normalized.map((item) => modelInputCapabilityOptions.find((option) => option.value === item)?.label ?? item);
}

function emptyProviderForm(capability: ProviderCapability): ProviderFormState {
  return {
    id: null,
    capability,
    input_capabilities: defaultInputCapabilities(capability),
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
    input_capabilities: normalizeInputCapabilities(provider.input_capabilities, capability),
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

function updateStatusLabel(status: string) {
  switch (status) {
    case "checking": return "检查中";
    case "available": return "有新版本";
    case "current": return "已是最新";
    case "error": return "检查失败";
    default: return "尚未检查";
  }
}

function formatCheckedAt(value: string | undefined) {
  if (!value) return "尚未检查";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function SettingsPage() {
  const {
    apiBaseUrl,
    checkForUpdates,
    loadProviders,
    providers,
    resolvedTheme,
    setThemeMode,
    themeMode,
    updateCheck
  } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [llmForm, setLlmForm] = useState<ProviderFormState>(() => emptyProviderForm("llm"));
  const [asrForm, setAsrForm] = useState<ProviderFormState>(() => emptyProviderForm("asr"));
  const [editing, setEditing] = useState<ProviderCapability | null>(null);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerTestingId, setProviderTestingId] = useState<string | null>(null);
  const [integrationTokens, setIntegrationTokens] = useState<ApiIntegrationToken[]>([]);
  const [tokenName, setTokenName] = useState("MCP 调用");
  const [createdToken, setCreatedToken] = useState<string | null>(null);
  const [editingTokenId, setEditingTokenId] = useState<string | null>(null);
  const [editingTokenName, setEditingTokenName] = useState("");
  const [tokenBusy, setTokenBusy] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);

  const llmProviders = providers.filter((provider) => capabilityOf(provider) === "llm");
  const asrProviders = providers.filter((provider) => capabilityOf(provider) === "asr");

  useEffect(() => {
    if (!providers.length) void loadProviders();
  }, [loadProviders, providers.length]);

  async function loadIntegrationTokens() {
    setTokenError(null);
    try {
      const result = await client.listIntegrationTokens();
      setIntegrationTokens(result.items);
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "读取集成令牌失败");
    }
  }

  useEffect(() => {
    void loadIntegrationTokens();
  }, [client]);

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
        input_capabilities: normalizeInputCapabilities(form.input_capabilities, form.capability),
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
        input_capabilities: normalizeInputCapabilities(provider.input_capabilities, capability),
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

  async function handleUpdateCheck() {
    const result = await checkForUpdates();
    if (result.status === "available") {
      showAppToast(`发现新版本 ${result.latestVersion}。`, "info");
    } else if (result.status === "current") {
      showAppToast("当前已经是最新版本。", "success");
    } else if (result.status === "error") {
      showAppToast(result.message ?? "更新检查失败。", "error");
    }
  }

  async function createToken() {
    const name = tokenName.trim();
    if (!name) {
      setTokenError("请输入令牌名称。");
      return;
    }
    setTokenBusy(true);
    setTokenError(null);
    setCreatedToken(null);
    try {
      const result = await client.createIntegrationToken(name, ["mcp:read"]);
      setCreatedToken(result.token);
      await loadIntegrationTokens();
      showAppToast("集成令牌已创建，只会显示这一次。", "success");
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "创建集成令牌失败");
    } finally {
      setTokenBusy(false);
    }
  }

  async function copyCreatedToken() {
    if (!createdToken) return;
    try {
      await navigator.clipboard.writeText(createdToken);
      showAppToast("令牌已复制。", "success");
    } catch {
      setTokenError("复制失败，请手动选中令牌。");
    }
  }

  async function deleteToken(tokenId: string) {
    setTokenBusy(true);
    setTokenError(null);
    try {
      await client.deleteIntegrationToken(tokenId);
      setIntegrationTokens((current) => current.filter((token) => token.id !== tokenId));
      showAppToast("集成令牌已删除。", "success");
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "删除集成令牌失败");
    } finally {
      setTokenBusy(false);
    }
  }

  function startRenameToken(token: ApiIntegrationToken) {
    setEditingTokenId(token.id);
    setEditingTokenName(token.name);
    setTokenError(null);
  }

  async function saveTokenName(tokenId: string) {
    const name = editingTokenName.trim();
    if (!name) {
      setTokenError("请输入令牌名称。");
      return;
    }
    setTokenBusy(true);
    setTokenError(null);
    try {
      const updated = await client.updateIntegrationToken(tokenId, name);
      setIntegrationTokens((current) => current.map((token) => (token.id === tokenId ? updated : token)));
      setEditingTokenId(null);
      setEditingTokenName("");
      showAppToast("集成令牌已重命名。", "success");
    } catch (e) {
      setTokenError(e instanceof Error ? e.message : "重命名集成令牌失败");
    } finally {
      setTokenBusy(false);
    }
  }

  function providerRow(provider: ApiProvider) {
    const capability = capabilityOf(provider);
    const isAsr = capability === "asr";
    const capabilityLabels = inputCapabilityLabels(provider.input_capabilities, capability);
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
          <div className="provider-row-meta">
            {capabilityLabels.map((label) => <span key={label} className="chip chip-neutral">{label}</span>)}
            {!isAsr && <span>{thinkingModeLabel(provider.thinking_mode)}</span>}
          </div>
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
        <div>
          <span className="text-caption">输入能力</span>
          <div className="input-capability-grid" role="group" aria-label="模型输入能力">
            {modelInputCapabilityOptions.map((option) => (
              <label key={option.value} className="checkbox-row input-capability-option">
                <input
                  type="checkbox"
                  checked={form.input_capabilities.includes(option.value)}
                  onChange={(event) => setForm((current) => {
                    const selected = new Set(current.input_capabilities);
                    if (event.target.checked) selected.add(option.value);
                    else selected.delete(option.value);
                    return {
                      ...current,
                      input_capabilities: normalizeInputCapabilities(Array.from(selected), current.capability),
                    };
                  })}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>
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
        <p className="page-lead">主题外观、模型服务与系统集成。</p>
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
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>system_update_alt</span>
            版本检查
          </div>
          <div className={`update-check-panel update-check-${updateCheck.status}`}>
            <div className="provider-icon">
              <span className="icon icon-sm">{updateCheck.status === "available" ? "new_releases" : updateCheck.status === "checking" ? "sync" : "verified"}</span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="update-check-title">
                {updateStatusLabel(updateCheck.status)}
                {updateCheck.status === "available" && <span className="chip chip-status-failed">新版本</span>}
              </div>
              <div className="text-meta">
                当前版本 {updateCheck.currentVersion}
                {updateCheck.latestVersion ? ` · 最新版本 ${updateCheck.latestVersion}` : ""}
                {" · "}
                上次检查 {formatCheckedAt(updateCheck.checkedAt)}
              </div>
              {updateCheck.message && <div className="text-caption update-check-message">{updateCheck.message}</div>}
              {updateCheck.status === "available" && updateCheck.notes && (
                <div className="text-caption update-check-notes">{updateCheck.notes.slice(0, 180)}{updateCheck.notes.length > 180 ? "…" : ""}</div>
              )}
            </div>
            <div className="update-check-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void handleUpdateCheck()} disabled={updateCheck.status === "checking"}>
                <span className="icon icon-sm">{updateCheck.status === "checking" ? "sync" : "refresh"}</span>
                立即检查
              </button>
              {updateCheck.releaseUrl && (
                <a className="btn btn-ghost btn-sm" href={updateCheck.releaseUrl} target="_blank" rel="noreferrer">
                  <span className="icon icon-sm">open_in_new</span>
                  查看版本
                </a>
              )}
            </div>
          </div>
          <p className="text-meta">OneRadar 会每 10 分钟自动检查一次，有可用更新时顶部设置按钮会显示红点。</p>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">
            <span className="icon icon-sm" style={{ marginRight: 8, color: "var(--tertiary)", verticalAlign: "middle" }}>key</span>
            集成令牌
          </div>
          <div className="settings-model-block">
            <div className="settings-model-block-header">
              <div>
                <h3>服务集成</h3>
                <p>用于 MCP 调用，令牌绑定当前账号，创建后只显示一次。</p>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, alignItems: "end" }}>
              <label>
                <span className="text-caption">令牌名称</span>
                <input className="input" value={tokenName} onChange={(event) => setTokenName(event.target.value)} />
              </label>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void createToken()} disabled={tokenBusy}>
                <span className="icon icon-sm">add</span>
                创建令牌
              </button>
            </div>
            {createdToken && (
              <div className="feedback feedback-success">
                <div style={{ fontWeight: 700, marginBottom: 6 }}>新令牌只显示一次</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <code style={{ flex: 1, wordBreak: "break-all" }}>{createdToken}</code>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => void copyCreatedToken()}>
                    复制
                  </button>
                </div>
              </div>
            )}
            <div className="stack-sm">
              {integrationTokens.length ? integrationTokens.map((token) => (
                <div key={token.id} className="provider-row">
                  <div className="provider-icon">
                    <span className="icon icon-sm">vpn_key</span>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {editingTokenId === token.id ? (
                      <input
                        className="input"
                        value={editingTokenName}
                        onChange={(event) => setEditingTokenName(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void saveTokenName(token.id);
                          if (event.key === "Escape") {
                            setEditingTokenId(null);
                            setEditingTokenName("");
                          }
                        }}
                        autoFocus
                      />
                    ) : (
                      <div style={{ fontWeight: 600, fontSize: 14, color: "var(--on-surface)" }}>{token.name}</div>
                    )}
                    <div style={{ fontSize: 12, color: "var(--outline)" }}>
                      {token.token_prefix}… · {token.scopes.join(", ")} · {token.last_used_at ? `上次使用 ${new Date(token.last_used_at).toLocaleString()}` : "尚未使用"}
                    </div>
                  </div>
                  {editingTokenId === token.id ? (
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => void saveTokenName(token.id)} disabled={tokenBusy || !editingTokenName.trim()}>
                        保存
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setEditingTokenId(null); setEditingTokenName(""); }} disabled={tokenBusy}>
                        取消
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => startRenameToken(token)} disabled={tokenBusy}>
                        重命名
                      </button>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => void deleteToken(token.id)} disabled={tokenBusy}>
                        删除
                      </button>
                    </div>
                  )}
                </div>
              )) : <p className="text-meta">还没有创建集成令牌。</p>}
            </div>
            {tokenError && <div className="feedback feedback-error">{tokenError}</div>}
          </div>
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
        </div>
      </div>
    </div>
  );
}
