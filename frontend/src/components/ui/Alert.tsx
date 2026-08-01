import type { ReactNode } from "react";

type AlertType = "info" | "warning" | "error";

const STYLES: Record<AlertType, string> = {
  info:    "bg-blue-50 text-blue-700 border-l-blue-400",
  warning: "bg-amber-50 text-amber-700 border-l-amber-400",
  error:   "bg-red-50 text-red-600 border-l-red-400",
};

interface Props {
  type?: AlertType;
  children: ReactNode;
  className?: string;
}

export default function Alert({ type = "info", children, className = "" }: Props) {
  return (
    <div className={`text-sm px-4 py-3 rounded-lg border-l-4 ${STYLES[type]} ${className}`}>
      {children}
    </div>
  );
}
