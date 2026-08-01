interface Props {
  value: number;
  max: number;
  size?: "sm" | "md";
}

function colorClasses(pct: number) {
  if (pct >= 85) return { bar: "bg-green-500", text: "text-green-600" };
  if (pct >= 70) return { bar: "bg-amber-500", text: "text-amber-600" };
  return { bar: "bg-red-500", text: "text-red-600" };
}

export default function ProgressBar({ value, max, size = "md" }: Props) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  const { bar, text } = colorClasses(pct);
  const height = size === "sm" ? "h-1.5" : "h-2";

  return (
    <div className="w-full">
      <div className={`w-full bg-gray-200 rounded-full overflow-hidden ${height}`}>
        <div
          className={`${height} rounded-full transition-all duration-700 ${bar}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={`text-xs font-medium mt-1 ${text}`}>{pct}%</div>
    </div>
  );
}
