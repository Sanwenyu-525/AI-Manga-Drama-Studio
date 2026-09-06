import { useEffect, useRef } from "react";
import { WarningCircle, Trash } from "@phosphor-icons/react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  details?: string[];
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Pro Max 规范的二次确认对话框：
 * - scrim 52-60% 黑，阻断误触
 * - 1px 边界 + 8px 圆角，暗色层级同 DESIGN.md
 * - 危险操作红色主按钮 + 次要取消，空间分离
 * - ESC / 点击遮罩关闭，焦点陷阱，首焦点落在取消
 * - 160-220ms transform+opacity 过渡，respect prefers-reduced-motion
 */
export function ConfirmDialog({
  open,
  title,
  description,
  details,
  confirmLabel = "确认",
  cancelLabel = "取消",
  variant = "danger",
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    // 首焦点：取消，避免误删（Pro Max destructive-emphasis）
    const t = window.setTimeout(() => cancelRef.current?.focus(), 30);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
      if (event.key === "Tab") {
        // 简易焦点循环：仅两个按钮
        const nodes = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    // 锁滚动
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="confirm-backdrop"
      role="presentation"
      onClick={onCancel}
      aria-hidden={false}
    >
      <div
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby={description ? "confirm-dialog-desc" : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="confirm-head">
          <span className={`confirm-icon ${variant}`}>
            {variant === "danger" ? <WarningCircle size={20} weight="fill" /> : <WarningCircle size={20} />}
          </span>
          <h3 id="confirm-dialog-title">{title}</h3>
        </div>

        {description && (
          <p id="confirm-dialog-desc" className="confirm-desc">
            {description}
          </p>
        )}

        {details && details.length > 0 && (
          <ul className="confirm-details">
            {details.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        )}

        <div className="confirm-actions">
          <button
            ref={cancelRef}
            type="button"
            className="btn secondary"
            onClick={onCancel}
            disabled={loading}
            autoFocus
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={`btn ${variant === "danger" ? "btn-danger" : "primary"}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? (
              "处理中…"
            ) : (
              <>
                <Trash size={14} weight="bold" /> {confirmLabel}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
