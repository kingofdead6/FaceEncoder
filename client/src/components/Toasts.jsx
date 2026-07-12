/** Toast stack (bottom-right) — success / error / info with auto-dismiss. */
import { FiAlertTriangle, FiCheckCircle, FiInfo, FiX } from "react-icons/fi";
import { useApp } from "../context/AppContext";

const VARIANTS = {
  success: { icon: FiCheckCircle, cls: "border-ok/40 text-ok" },
  error: { icon: FiAlertTriangle, cls: "border-danger/40 text-danger" },
  info: { icon: FiInfo, cls: "border-signal/40 text-signal" },
};

export default function Toasts() {
  const { toasts, dismissToast } = useApp();

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,360px)] flex-col gap-2"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((t) => {
        const v = VARIANTS[t.variant] ?? VARIANTS.info;
        const Icon = v.icon;
        return (
          <div
            key={t.id}
            className={`toast-in pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-panel p-3 shadow-lg ${v.cls}`}
            role="status"
          >
            <Icon className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="flex-1 text-sm text-ink">{t.message}</p>
            <button
              type="button"
              onClick={() => dismissToast(t.id)}
              className="text-muted transition-colors hover:text-ink"
              aria-label="Dismiss notification"
            >
              <FiX />
            </button>
          </div>
        );
      })}
    </div>
  );
}
