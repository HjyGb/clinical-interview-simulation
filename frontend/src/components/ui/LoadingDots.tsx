interface Props {
  text?: string;
}

export default function LoadingDots({ text = "加载中..." }: Props) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
      <span className="flex gap-1">
        <span className="w-1.5 h-1.5 bg-[var(--color-primary)] rounded-full animate-bounce" />
        <span
          className="w-1.5 h-1.5 bg-[var(--color-primary)] rounded-full animate-bounce"
          style={{ animationDelay: "150ms" }}
        />
        <span
          className="w-1.5 h-1.5 bg-[var(--color-primary)] rounded-full animate-bounce"
          style={{ animationDelay: "300ms" }}
        />
      </span>
      {text}
    </span>
  );
}
