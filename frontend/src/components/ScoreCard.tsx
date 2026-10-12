import type { AssessmentReport, ScoringItem } from '../types';
import ProgressBar from './ui/ProgressBar';

interface Props {
  report: AssessmentReport;
}

const STATUS_LABEL: Record<string, string> = {
  ne: '不可评价',
  na: '本例不适用',
  skipped_safety: '安全早停',
};

/** 安全通道：独立置顶。**不进任何分数**，也不与沟通表现相互抵消。 */
function SafetyBanner({ report }: { report: AssessmentReport }) {
  const s = report.safety;
  if (!s.requires_review) return null;
  const hits = s.flags.filter((f) => f.hit);
  const unchecked = s.flags.filter((f) => !f.checked);

  return (
    <div className="rounded-xl border-2 border-red-300 bg-red-50 p-4 mb-5">
      <h3 className="text-sm font-semibold text-red-700 mb-2 flex items-center gap-1.5">
        ⚠ 需人工复核
      </h3>
      {hits.map((f) => (
        <div key={f.index} className="mb-2">
          <p className="text-sm text-red-800 font-medium">关键错误 {f.index}：{f.error}</p>
          {f.evidence_quote && (
            <p className="text-xs text-red-700 mt-0.5 pl-3 border-l-2 border-red-300">
              学员原话：{f.evidence_quote}
            </p>
          )}
        </div>
      ))}
      {unchecked.map((f) => (
        <p key={f.index} className="text-xs text-amber-700">
          未能复核「{f.error}」——系统侧未跑成，<strong>不等于没犯</strong>。
        </p>
      ))}
      {s.safety_priority_case && (
        <p className="text-xs text-red-700 mt-2">
          【安全优先例】已识别危险并转诊；未完成的条目按「安全早停」处理，不以未跑完清单扣分。
        </p>
      )}
      <p className="text-xs text-red-600 mt-2 pt-2 border-t border-red-200">
        安全标记不参与计分，也不与沟通表现相互抵消。
      </p>
    </div>
  );
}

function ItemLine({ item, label }: { item: ScoringItem; label: string }) {
  const unscored = item.status !== 'scored';
  const quote = item.evidence.find((e) => e.quote)?.quote || '';
  const detail = quote || item.note;
  return (
    <div className="mb-3">
      <div className="flex justify-between items-baseline gap-2 mb-0.5">
        <span className="text-xs font-medium text-[var(--color-text)]">
          <span className="font-mono text-[var(--color-text-secondary)] mr-1">{item.id}</span>
          {label}
        </span>
        {unscored ? (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 shrink-0">
            {STATUS_LABEL[item.status] ?? item.status}
          </span>
        ) : (
          <span className="text-xs font-semibold text-[var(--color-text)] shrink-0">
            {item.score}/{item.max_score}
          </span>
        )}
      </div>
      {!unscored && <ProgressBar value={item.score} max={item.max_score} size="sm" />}
      {detail && (
        <p className="text-[11px] text-[var(--color-text-secondary)] mt-1 leading-relaxed line-clamp-3">
          {detail}
        </p>
      )}
    </div>
  );
}

export default function ScoreCard({ report }: Props) {
  const byId = new Map(report.items.map((i) => [i.id, i]));
  const { total } = report;

  return (
    <div>
      <SafetyBanner report={report} />

      {/* 计数条：原始分要连带可评上限一起说，避免把 NE/NA 读成"丢了分" */}
      <div className="bg-white rounded-xl p-4 mb-5 shadow-sm border border-[var(--color-border)] text-center">
        <div className="text-3xl font-bold text-[var(--color-primary)]">
          {total.raw_total}
          <span className="text-base font-normal text-[var(--color-text-secondary)]">
            {' '}/ {total.raw_max_counted}
          </span>
        </div>
        <p className="text-xs text-[var(--color-text-secondary)] mt-1">
          原始分 / 可评上限（名义满分 {total.raw_max_nominal}）
        </p>
        {Object.keys(total.excluded).length > 0 && (
          <p className="text-[11px] text-amber-600 mt-1">
            未计入：{Object.entries(total.excluded)
              .map(([k, ids]) => `${STATUS_LABEL[k] ?? k} ${ids.join('/')}`)
              .join('、')}
          </p>
        )}
        {report.system_errors > 0 && (
          <p className="text-[11px] text-amber-600 mt-1">
            会话中有 {report.system_errors} 次系统侧失败，未折算为失分
          </p>
        )}
        <p className="text-[10px] text-[var(--color-text-secondary)] mt-2">{report.scoring_note}</p>
      </div>

      {report.views.map((view) => (
        <div
          key={view.name}
          className="bg-white rounded-xl p-5 mb-5 shadow-sm border border-[var(--color-border)]"
        >
          <h3 className="text-base font-semibold text-[var(--color-text)] mb-4">{view.name}</h3>
          {view.groups.map((g) => (
            <div key={g.name} className="mb-5 last:mb-0">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-semibold text-[var(--color-text)]">{g.name}</span>
                <span className="text-sm font-semibold text-[var(--color-primary)]">
                  {g.score}/{g.max}
                </span>
              </div>
              {g.items.map((rid) => {
                const it = byId.get(rid);
                return it ? <ItemLine key={rid} item={it} label={it.name} /> : null;
              })}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
