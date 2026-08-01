import type { AssessmentBlock, ScoreDimension } from '../types';
import ProgressBar from './ui/ProgressBar';

interface Props {
  title: string;
  block: AssessmentBlock;
}

function DimensionRow({ dim }: { dim: ScoreDimension }) {
  const pct = Math.round((dim.score / dim.max_score) * 100);
  const color =
    pct >= 85 ? 'text-green-600' : pct >= 70 ? 'text-amber-600' : 'text-red-600';

  return (
    <div className="mb-4">
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-[var(--color-text)]">{dim.name}</span>
        <span className={`text-sm font-semibold ${color}`}>
          {dim.score}/{dim.max_score}
        </span>
      </div>
      <ProgressBar value={dim.score} max={dim.max_score} size="sm" />
      <p className="text-xs text-[var(--color-text-secondary)] mt-1.5 leading-relaxed">
        {dim.justification}
      </p>
      {dim.missed_items && dim.missed_items.length > 0 && (
        <p className="text-xs text-[var(--color-error)] mt-1">
          遗漏：{dim.missed_items.join('、')}
        </p>
      )}
      {dim.suggestions && dim.suggestions.length > 0 && (
        <p className="text-xs text-[var(--color-primary)] mt-1">
          建议：{dim.suggestions.join('；')}
        </p>
      )}
    </div>
  );
}

export default function ScoreCard({ title, block }: Props) {
  const pct =
    block.max_score > 0
      ? Math.round((block.total_score / block.max_score) * 100)
      : 0;
  const color =
    pct >= 85
      ? 'text-green-600'
      : pct >= 70
        ? 'text-amber-600'
        : 'text-red-600';

  return (
    <div className="bg-white rounded-xl p-6 mb-5 shadow-sm border border-[var(--color-border)]">
      <div className="flex justify-between items-center mb-5">
        <h3 className="text-base font-semibold text-[var(--color-text)] m-0">{title}</h3>
        <span className={`text-2xl font-bold ${color}`}>
          {block.total_score}
          <span className="text-sm font-normal text-[var(--color-text-secondary)]">
            /{block.max_score}
          </span>
        </span>
      </div>
      {block.dimensions.map((dim) => (
        <DimensionRow key={dim.name} dim={dim} />
      ))}
    </div>
  );
}
