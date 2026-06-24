import { FormEvent, useEffect, useMemo, useState } from "react";
import { createApiClient } from "../api";
import type { ApiIntegrationToken } from "../api/types";
import { useAppState } from "../state/appState";

function apiRootUrl(baseUrl: string) {
  const normalized = baseUrl.trim().replace(/\/+$/, "");
  return normalized.endsWith("/api") ? normalized.slice(0, -4) : normalized;
}

function displayTime(value?: string | null) {
  if (!value) return "从未使用";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function copyText(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value);
    window.dispatchEvent(new CustomEvent("oneradar:toast", { detail: { message: `已复制${label}`, tone: "success" } }));
  } catch {
    window.prompt(`复制${label}`, value);
  }
}

export function ApiConsolePage() {
  const { apiBaseUrl } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [tokens, setTokens] = useState<ApiIntegrationToken[]>([]);
  const [tokenName, setTokenName] = useState("OneRadar API");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootUrl = apiRootUrl(apiBaseUrl);
  const mcpUrl = `${rootUrl}/api/mcp`;
  const analysisUrl = `${rootUrl}/api/analysis/url`;

  async function loadTokens() {
    setError(null);
    try {
      const response = await client.listIntegrationTokens();
      setTokens(response.items);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "读取调用令牌失败");
    }
  }

  useEffect(() => {
    void loadTokens();
  }, [client]);

  async function createToken(event: FormEvent) {
    event.preventDefault();
    const name = tokenName.trim();
    if (!name) return;
    setBusy(true);
    setError(null);
    setNewToken(null);
    try {
      const response = await client.createIntegrationToken(name, ["mcp:read", "analysis:write"]);
      setNewToken(response.token);
      await loadTokens();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "创建令牌失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteToken(tokenId: string) {
    setBusy(true);
    setError(null);
    try {
      await client.deleteIntegrationToken(tokenId);
      setTokens((current) => current.filter((token) => token.id !== tokenId));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "删除令牌失败");
    } finally {
      setBusy(false);
    }
  }

  const analysisExample = `curl -X POST "${analysisUrl}" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com/article"}'`;

  return (
    <div className="page api-console-page">
      <div className="page-header">
        <p className="page-eyebrow">API / MCP</p>
        <h2 className="page-title">调用接口</h2>
        <p className="page-lead">OneRadar 的新闻源和临时分析能力可以被其他产品、Obsidian 工作流或 AI Agent 调用。</p>
      </div>

      {error && <div className="feedback feedback-error">{error}</div>}

      <div className="api-console-grid">
        <section className="api-console-panel api-console-primary">
          <div className="card-header">
            <span className="card-title">入口</span>
            <span className="chip chip-success">已内置</span>
          </div>
          <div className="api-endpoint-list">
            <div>
              <span>MCP JSON-RPC</span>
              <code>{mcpUrl}</code>
              <p>供 Hermes Agent 或其他 MCP 客户端读取 RSS 源状态和时间窗口新闻。</p>
            </div>
            <div>
              <span>临时链接分析</span>
              <code>{analysisUrl}</code>
              <p>提交 URL，返回正文/简介、摘要和结构化结果，不创建阅读库条目。</p>
            </div>
          </div>
        </section>

        <section className="api-console-panel">
          <div className="card-header">
            <span className="card-title">能力表</span>
          </div>
          <div className="capability-list">
            <span><strong>RSS 新闻</strong> 源状态、缓存条目、日报候选数据</span>
            <span><strong>每日新闻</strong> 按日期生成、分享、浏览</span>
            <span><strong>网页/公众号</strong> 临时正文提取和摘要</span>
            <span><strong>Bilibili</strong> 临时元数据/简介分析，转写适配器后续接入</span>
            <span><strong>YouTube / 抖音 / 小红书</strong> 平台适配器待接入</span>
          </div>
        </section>
      </div>

      <section className="api-console-panel">
        <div className="card-header">
          <span className="card-title">调用令牌</span>
          <span className="text-caption">创建后只显示一次</span>
        </div>
        <form className="api-token-form" onSubmit={(event) => void createToken(event)}>
          <input className="input" value={tokenName} onChange={(event) => setTokenName(event.target.value)} placeholder="令牌名称" />
          <button className="btn btn-primary btn-sm" disabled={busy || !tokenName.trim()} type="submit">
            <span className="icon icon-sm">{busy ? "sync" : "add"}</span>
            创建令牌
          </button>
        </form>
        {newToken && (
          <div className="api-token-secret">
            <code>{newToken}</code>
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => void copyText(newToken, "令牌")}>
              <span className="icon icon-sm">content_copy</span>
              复制
            </button>
          </div>
        )}
        <div className="api-token-list">
          {tokens.length === 0 && <p className="text-caption">还没有令牌。</p>}
          {tokens.map((token) => (
            <div key={token.id} className="api-token-row">
              <div>
                <strong>{token.name}</strong>
                <span>{token.token_prefix}... · {token.scopes.join(", ")} · 最后使用 {displayTime(token.last_used_at)}</span>
              </div>
              <button className="btn btn-danger btn-sm" type="button" disabled={busy} onClick={() => void deleteToken(token.id)}>
                删除
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="api-console-panel">
        <div className="card-header">
          <span className="card-title">示例</span>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => void copyText(analysisExample, "示例请求")}>
            <span className="icon icon-sm">content_copy</span>
            复制
          </button>
        </div>
        <pre className="api-example">{analysisExample}</pre>
      </section>
    </div>
  );
}
