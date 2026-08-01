import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { listCases } from '../api/cases';
import { createSession } from '../api/sessions';
import { useInterviewStore } from '../stores/interviewStore';
import DifficultyBadge from '../components/ui/DifficultyBadge';
import LoadingDots from '../components/ui/LoadingDots';
import type { CaseSummary } from '../types';

export default function CaseListPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState<number | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const setSession = useInterviewStore((s) => s.setSession);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }
    listCases()
      .then((res) => setCases(res.cases))
      .catch((err) => {
        console.error(err);
        if ((err as Error).message.includes('401') || (err as Error).message.includes('登录')) {
          navigate('/login');
        }
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  const handleSelect = async (c: CaseSummary) => {
    setCreating(c.id);
    try {
      const session = await createSession(c.id);
      setSession(session.id, session.max_rounds);
      navigate(`/interview/${session.id}`);
    } catch (e) {
      alert(`创建会话失败：${(e as Error).message}`);
    } finally {
      setCreating(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingDots text="加载病例列表中..." />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-10 px-4">
      {/* Navigation tabs */}
      <div className="flex items-center gap-6 mb-6 border-b border-[var(--color-border)] pb-0">
        <button
          onClick={() => navigate('/cases')}
          className={`text-sm font-medium pb-2.5 border-b-2 transition-colors
            ${location.pathname === '/cases'
              ? 'text-[var(--color-primary)] border-[var(--color-primary)]'
              : 'text-[var(--color-text-secondary)] border-transparent hover:text-[var(--color-text)]'}`}
        >
          📋 病例列表
        </button>
        <button
          onClick={() => navigate('/history')}
          className="text-sm font-medium pb-2.5 border-b-2 border-transparent
                     text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
        >
          📜 历史记录
        </button>
      </div>

      <h1 className="text-2xl font-bold text-[var(--color-text)] mb-2">
        选择练习病例
      </h1>
      <p className="text-sm text-[var(--color-text-secondary)] mb-6">
        选择一个病例开始 AI 问诊练习。每个病例有不同的难度和疾病类型。
      </p>

      <div className="flex flex-col gap-4">
        {cases.map((c) => (
          <div
            key={c.id}
            onClick={() => creating === null && handleSelect(c)}
            className={`p-5 border border-[var(--color-border)] rounded-xl
                        transition-colors cursor-pointer
                        hover:border-blue-200 hover:bg-blue-50/50 hover:shadow-sm
                        ${creating === c.id ? 'opacity-60 pointer-events-none' : ''}`}
          >
            <div className="flex justify-between items-start">
              <h3 className="text-lg font-semibold text-[var(--color-text)] m-0">
                {c.title}
              </h3>
              <DifficultyBadge difficulty={c.difficulty} />
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mt-2 line-clamp-2">
              {c.chief_complaint || '（病例详情请点击查看）'}
            </p>
            <div className="flex gap-3 mt-3 text-xs text-[var(--color-text-secondary)]">
              <span>🏥 {c.department}</span>
              <span>{c.visit_type}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
