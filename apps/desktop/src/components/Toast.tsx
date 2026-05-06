export type ToastState = {
  message: string;
  tone?: "success" | "error" | "info";
} | null;

export function Toast({ toast, onClose }: { toast: ToastState; onClose?: () => void }) {
  if (!toast) return null;
  const tone = toast.tone ?? "info";
  return (
    <div className={`app-toast app-toast-${tone}`} role="status">
      <span className="icon icon-sm">{tone === "error" ? "error" : tone === "success" ? "check_circle" : "info"}</span>
      <span>{toast.message}</span>
      {onClose && (
        <button type="button" aria-label="关闭提示" onClick={onClose}>
          <span className="icon icon-sm">close</span>
        </button>
      )}
    </div>
  );
}
