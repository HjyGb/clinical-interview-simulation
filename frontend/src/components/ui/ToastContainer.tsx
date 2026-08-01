import { useToastStore } from "../../stores/toastStore";

const COLORS: Record<
  string,
  { border: string; bg: string; text: string; icon: string }
> = {
  success: {
    border: "border-l-green-400",
    bg: "bg-green-50",
    text: "text-green-800",
    icon: "✅",
  },
  error: {
    border: "border-l-red-400",
    bg: "bg-red-50",
    text: "text-red-800",
    icon: "❌",
  },
  warning: {
    border: "border-l-amber-400",
    bg: "bg-amber-50",
    text: "text-amber-800",
    icon: "⚠️",
  },
  info: {
    border: "border-l-blue-400",
    bg: "bg-blue-50",
    text: "text-blue-800",
    icon: "ℹ️",
  },
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => {
        const c = COLORS[t.type];
        return (
          <div
            key={t.id}
            className={`animate-slide-in pointer-events-auto flex items-center gap-2 px-4 py-3
                        rounded-lg border-l-4 shadow-md min-w-[280px] max-w-[420px]
                        ${c.border} ${c.bg} ${c.text}`}
          >
            <span className="shrink-0 text-sm">{c.icon}</span>
            <span className="text-sm flex-1">{t.message}</span>
            <button
              onClick={() => removeToast(t.id)}
              className="text-sm opacity-60 hover:opacity-100 shrink-0 leading-none"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
