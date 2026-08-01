const STATUS_MAP: Record<string, { label: string; classes: string }> = {
  active:    { label: "进行中", classes: "bg-green-100 text-green-700" },
  ended:     { label: "已结束", classes: "bg-gray-100 text-gray-500" },
  diagnosed: { label: "已诊断", classes: "bg-blue-100 text-blue-700" },
  evaluated: { label: "已评估", classes: "bg-purple-100 text-purple-700" },
};

interface Props {
  status: string;
}

export default function StatusBadge({ status }: Props) {
  const item = STATUS_MAP[status] || { label: status, classes: "bg-gray-100 text-gray-600" };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${item.classes}`}>
      {item.label}
    </span>
  );
}
