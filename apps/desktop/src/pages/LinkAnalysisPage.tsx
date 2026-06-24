import { FormEvent, useMemo, useState } from "react";
import { createApiClient } from "../api";
import type { ApiUrlAnalysisResponse } from "../api/types";
import { useAppState } from "../state/appState";

type ResultTab = "summary" | "original" | "json";

function normalizeUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
}

function displayTime(value?: string | null) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function compactHost(value?: string | null) {
  if (!value) return "未知来源";
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function buildMarkdown(result: ApiUrlAnalysisResponse) {
  return [
    `# ${result.title}`,
    "",
    `- 来源：${result.source_name || compactHost(result.final_url || result.source_url)}`,
    `- 链接：${result.final_url || result.source_url}`,
    `- 平台：${result.platform}`,
    `- 时间：${displayTime(result.published_at)}`,
    "",
    "## 摘要",
    "",
    result.summary,
    "",
    "## 原文",
    "",
    result.original_text,
  ].join("\n");
}

async function copyText(value: string, label: string) {
  try {
    await navigator.clipboard.writeText(value);
    window.dispatchEvent(new CustomEvent("oneradar:toast", { detail: { message: `已复制${label}`, tone: "success" } }));
  } catch {
    window.prompt(`复制${label}`, value);
  }
}

export function LinkAnalysisPage() {
  const { apiBaseUrl, providers, loadProviders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiUrlAnalysisResponse | null>(null);
  const [tab, setTab] = useState<ResultTab>("summary");

  const hasLlm = providers.some((provider) => provider.capability !== "asr" && provider.is_enabled && provider.api_key_configured && provider.chat_model);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = normalizeUrl(url);
    if (!normalized) {
      setError("请先粘贴一个链接。");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (!providers.length) {
        await loadProviders();
      }
      const next = await client.analyzeUrl(normalized);
      setResult(next);
      setUrl(next.final_url || next.source_url);
      setTab("summary");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "链接分析失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page link-analysis-page">
      <div className="page-header">
        <p className="page-eyebrow">Link Analysis</p>
        <h2 className="page-title">链接分析</h2>
        <p className="page-lead">粘贴链接后临时提取正文、平台信息和摘要。结果默认不保存到 OneRadar。</p>
      </div>

      <section className="analysis-console">
        <form className="analysis-url-bar" onSubmit={(event) => void submit(event)}>
          <span className="icon">travel_explore</span>
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="粘贴网页、微信公众号、Bilibili 链接"
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={busy}>
            <span className="icon icon-sm">{busy ? "sync" : "bolt"}</span>
            {busy ? "分析中..." : "分析"}
          </button>
        </form>
        <div className="analysis-capability-row">
          <span className={`chip ${hasLlm ? "chip-success" : "chip-neutral"}`}>
            {hasLlm ? "当前 LLM 可用于摘要" : "未配置 LLM 时使用摘录摘要"}
          </span>
          <span className="chip chip-neutral">网页 / 微信公众号：正文提取</span>
          <span className="chip chip-neutral">Bilibili：元数据分析</span>
          <span className="chip chip-neutral">YouTube / 抖音 / 小红书：适配器待接入</span>
        </div>
      </section>

      {error && <div className="feedback feedback-error">{error}</div>}

      {!result && !error && (
        <div className="empty-state analysis-empty">
          <div className="empty-state-icon"><span className="icon icon-lg">hub</span></div>
          <h3>等待链接</h3>
          <p>这里是临时分析台，不产生阅读进度、文件夹、笔记或知识库条目。</p>
        </div>
      )}

      {result && (
        <section className="analysis-result">
          <header className="analysis-result-header">
            <div>
              <p className="page-eyebrow">{result.platform} · {result.content_type}</p>
              <h3>{result.title}</h3>
              <div className="analysis-meta">
                <span>{result.source_name || compactHost(result.final_url || result.source_url)}</span>
                {result.author && <span>{result.author}</span>}
                <span>{displayTime(result.published_at)}</span>
                <span>{result.persisted ? "已保存" : "未保存"}</span>
              </div>
            </div>
            <div className="analysis-actions">
              <a className="btn btn-secondary btn-sm" href={result.final_url || result.source_url} target="_blank" rel="noreferrer">
                <span className="icon icon-sm">open_in_new</span>
                原文
              </a>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copyText(buildMarkdown(result), "Markdown")}>
                <span className="icon icon-sm">content_copy</span>
                Markdown
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copyText(JSON.stringify(result, null, 2), "JSON")}>
                <span className="icon icon-sm">data_object</span>
                JSON
              </button>
            </div>
          </header>

          <div className="analysis-tabs">
            {([
              ["summary", "摘要"],
              ["original", result.source_text_kind === "metadata_description" ? "平台简介" : "原文"],
              ["json", "结构化"],
            ] as [ResultTab, string][]).map(([value, label]) => (
              <button key={value} type="button" className={tab === value ? "active" : ""} onClick={() => setTab(value)}>
                {label}
              </button>
            ))}
          </div>

          <div className="analysis-output">
            {tab === "summary" && (
              <article>
                <p className="analysis-provider">摘要来源：{result.summary_provider}{result.model_name ? ` · ${result.model_name}` : ""}</p>
                <div className="analysis-text">{result.summary}</div>
              </article>
            )}
            {tab === "original" && <pre>{result.original_text}</pre>}
            {tab === "json" && <pre>{JSON.stringify(result, null, 2)}</pre>}
          </div>
        </section>
      )}
    </div>
  );
}
