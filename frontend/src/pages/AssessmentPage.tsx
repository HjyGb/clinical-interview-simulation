import { useEffect, useState } from 'react';
import { useLocation, useParams, useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { getAssessment } from '../api/assessments';
import ScoreCard from '../components/ScoreCard';
import LoadingDots from '../components/ui/LoadingDots';
import type { AssessmentResult } from '../types';

export default function AssessmentPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const location = useLocation();
  const navigate = useNavigate();
  const [result, setResult] = useState<AssessmentResult | null>(
    (location.state as { result?: AssessmentResult })?.result || null,
  );
  const [loading, setLoading] = useState(!result);

  useEffect(() => {
    if (!result) {
      getAssessment(sessionId)
        .then(setResult)
        .catch(console.error)
        .finally(() => setLoading(false));
    }
  }, [sessionId, result]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3 text-[var(--color-text-secondary)]">
        <span className="text-4xl">📊</span>
        <p className="text-lg font-medium">正在生成评估报告...</p>
        <LoadingDots text="正在逐条对照评分锚点" />
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-lg text-[var(--color-text-secondary)]">无法加载评估结果</p>
        <button
          onClick={() => navigate('/cases')}
          className="px-6 py-2.5 rounded-lg font-medium text-sm transition-all
                     bg-[var(--color-primary)] text-white hover:opacity-90 active:scale-[0.98]"
        >
          返回病例列表
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <div className="text-center mb-6">
        <h1 className="text-2xl font-bold text-[var(--color-text)] mb-1">📊 评估报告</h1>
        <p className="text-sm text-[var(--color-text-secondary)]">
          依据 R01–R14 逐项评分 · 临床能力与沟通人文分别呈现
        </p>
      </div>

      <ScoreCard report={result.report} />

      <div className="flex justify-center gap-3 mt-6">
        <button
          onClick={() => navigate('/cases')}
          className="flex items-center gap-1.5 px-6 py-2.5 rounded-lg font-medium text-sm
                     transition-all active:scale-[0.98]
                     bg-[var(--color-primary)] text-white hover:opacity-90"
        >
          <RefreshCw className="w-4 h-4" />
          练习其他病例
        </button>
      </div>
    </div>
  );
}
