const DIFFICULTY_MAP: Record<string, { label: string; classes: string }> = {
  beginner:     { label: "初级", classes: "bg-green-50 text-green-600" },
  intermediate: { label: "中级", classes: "bg-amber-50 text-amber-600" },
  advanced:     { label: "高级", classes: "bg-red-50 text-red-600" },
};

interface Props {
  difficulty: string;
}

export default function DifficultyBadge({ difficulty }: Props) {
  const item = DIFFICULTY_MAP[difficulty] || {
    label: difficulty,
    classes: "bg-gray-50 text-gray-500",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${item.classes}`}>
      {item.label}
    </span>
  );
}
