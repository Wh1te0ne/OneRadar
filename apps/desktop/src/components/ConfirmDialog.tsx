type ConfirmDialogProps = {
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  title,
  body,
  confirmLabel = "确认",
  cancelLabel = "取消",
  busy = false,
  danger = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <div className="confirm-dialog-backdrop" role="presentation" onClick={() => !busy && onCancel()}>
      <div
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className={`confirm-dialog-icon ${danger ? "danger" : ""}`}>
          <span className="icon icon-sm">{danger ? "delete" : "help"}</span>
        </div>
        <div className="confirm-dialog-copy">
          <h3 id="confirm-dialog-title">{title}</h3>
          <p>{body}</p>
        </div>
        <div className="confirm-dialog-actions">
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn btn-sm ${danger ? "btn-danger" : "btn-primary"}`}
            disabled={busy}
            onClick={onConfirm}
          >
            <span className="icon icon-sm">{busy ? "sync" : danger ? "delete" : "check"}</span>
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
