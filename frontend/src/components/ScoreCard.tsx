import type { AssessmentBlock, ScoreDimension } from '../types';

interface Props {
  title: string;
  block: AssessmentBlock;
}

function DimensionRow({ dim }: { dim: ScoreDimension }) {
  const pct = Math.round((dim.score / dim.max_score) * 100);
  const color = pct >= 80 ? '#52c41a' : pct >= 60 ? '#faad14' : '#ff4d4f';
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontWeight: 500 }}>{dim.name}</span>
        <span style={{ color, fontWeight: 600 }}>
          {dim.score}/{dim.max_score}
        </span>
      </div>
      <div style={{
        height: 8,
        background: '#f0f0f0',
        borderRadius: 4,
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: color,
          borderRadius: 4,
          transition: 'width 0.5s ease',
        }} />
      </div>
      <p style={{ fontSize: 13, color: '#666', margin: '4px 0 0' }}>{dim.justification}</p>
      {dim.missed_items.length > 0 && (
        <p style={{ fontSize: 12, color: '#ff4d4f', margin: '4px 0 0' }}>
          遗漏：{dim.missed_items.join('、')}
        </p>
      )}
      {dim.suggestions.length > 0 && (
        <p style={{ fontSize: 12, color: '#1677ff', margin: '4px 0 0' }}>
          建议：{dim.suggestions.join('；')}
        </p>
      )}
    </div>
  );
}

export default function ScoreCard({ title, block }: Props) {
  return (
    <div style={{
      background: '#fff',
      borderRadius: 12,
      padding: 24,
      marginBottom: 20,
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        <span style={{
          fontSize: 24,
          fontWeight: 700,
          color: block.total_score >= 80 ? '#52c41a' : block.total_score >= 60 ? '#faad14' : '#ff4d4f',
        }}>
          {block.total_score}<span style={{ fontSize: 14, color: '#999' }}>/{block.max_score}</span>
        </span>
      </div>
      {block.dimensions.map((dim) => (
        <DimensionRow key={dim.name} dim={dim} />
      ))}
    </div>
  );
}
