import { useEffect, useMemo, useState } from "react";
import { createApiClient } from "../api";
import type { ApiItemSummary } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Toast, type ToastState } from "../components/Toast";
import { useAppState } from "../state/appState";

function formatTime(value?: string | null) {
  if (!value) return "未知";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fallbackSummary(item: ApiItemSummary) {
  return item.summary?.trim() || "已移入最近删除。";
}

export function TrashPage() {
  const { apiBaseUrl, loadFolders } = useAppState();
  const client = useMemo(() => createApiClient(apiBaseUrl), [apiBaseUrl]);
  const [items, setItems] = useState<ApiItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState>(null);
  const [pendingPurge, setPendingPurge] = useState<ApiItemSummary | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function showToast(message: string, tone: NonNullable<ToastState>["tone"] = "info") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 2600);
  }

  async function loadTrash() {
    setLoading(true);
    setError(null);
    try {
      const response = await client.listDeletedItems(200);
      setItems(response.items);
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "无法加载最近删除");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTrash();
  }, [client]);

  async function restoreItem(item: ApiItemSummary) {
    setBusyId(item.id);
    try {
      await client.restoreItem(item.id);
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      await loadFolders();
      showToast("已恢复", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "恢复失败", "error");
    } finally {
      setBusyId(null);
    }
  }

  async function purgeItem() {
    if (!pendingPurge) return;
    const item = pendingPurge;
    setBusyId(item.id);
    try {
      await client.purgeItem(item.id);
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      await loadFolders();
      setPendingPurge(null);
      showToast("已永久删除", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "永久删除失败", "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.18)",
        background: "var(--surface-lowest)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="icon" style={{ color: "var(--outline)" }}>delete</span>
          <h2 style={{ fontFamily: "Manrope, sans-serif", fontSize: 16, fontWeight: 700, margin: 0 }}>
            最近删除
          </h2>
          <span style={{ fontSize: 12, color: "var(--outline)" }}>{items.length} 条</span>
        </div>
        <span className="chip chip-neutral">保留 7 天</span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "4px 0" }}>
        {error && <div className="feedback feedback-error" style={{ margin: "16px 28px" }}>{error}</div>}
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <span className="icon icon-lg" style={{ color: "var(--outline)" }}>sync</span>
          </div>
        )}
        {!loading && items.length === 0 && (
          <div className="empty-state" style={{ marginTop: 80 }}>
            <div className="empty-state-icon"><span className="icon icon-lg">delete</span></div>
            <h3>最近删除为空</h3>
            <p>删除的内容会在这里保留 7 天。</p>
          </div>
        )}
        {items.map((item) => (
          <div
            key={item.id}
            style={{
              display: "flex", alignItems: "flex-start", gap: 14,
              padding: "13px 28px", borderBottom: "1px solid rgba(var(--outline-rgb),0.12)",
            }}
          >
            <span className="icon icon-sm" style={{ color: "var(--outline)", marginTop: 2 }}>
              {item.content_type === "bilibili_video" ? "smart_display" : "article"}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                <span style={{ fontSize: 12, fontWeight: 650, color: "var(--on-surface-v)" }}>{item.folder_name}</span>
                <span style={{ fontSize: 11, color: "var(--outline)" }}>删除于 {formatTime(item.deleted_at)}</span>
                <span style={{ fontSize: 11, color: "var(--outline)" }}>保留至 {formatTime(item.delete_expires_at)}</span>
              </div>
              <h3 style={{
                margin: "0 0 4px", fontSize: 14.5, lineHeight: 1.35,
                fontFamily: "Manrope, sans-serif", fontWeight: 740, color: "var(--on-surface)",
              }}>
                {item.title}
              </h3>
              <p style={{
                margin: 0, color: "var(--on-surface-v)", fontSize: 13, lineHeight: 1.6,
                display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
              }}>
                {fallbackSummary(item)}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              <button type="button" className="btn btn-ghost btn-sm" disabled={busyId === item.id} onClick={() => void restoreItem(item)}>
                <span className="icon icon-sm">restore_from_trash</span>
                恢复
              </button>
              <button type="button" className="btn btn-danger btn-sm" disabled={busyId === item.id} onClick={() => setPendingPurge(item)}>
                <span className="icon icon-sm">delete_forever</span>
                永久删除
              </button>
            </div>
          </div>
        ))}
      </div>

      {pendingPurge && (
        <ConfirmDialog
          title="永久删除"
          body={`确定永久删除「${pendingPurge.title}」吗？这个操作不能撤销。`}
          confirmLabel="永久删除"
          danger
          busy={busyId === pendingPurge.id}
          onCancel={() => {
            if (!busyId) setPendingPurge(null);
          }}
          onConfirm={() => void purgeItem()}
        />
      )}
      <Toast toast={toast} onClose={() => setToast(null)} />
    </div>
  );
}
