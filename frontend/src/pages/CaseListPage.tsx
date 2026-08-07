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
  const [search, setSearch] = useState('');
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

  // Client-side search filter
  const filteredCases = search.trim()
    ? cases.filter((c) =>
        c.title.includes(search) ||
        c.chief_complaint?.includes(search) ||
        c.department.includes(search) ||
        c.case_number?.includes(search)
      )
    : cases;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingDots text="加载病例列表中..." />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4 h-screen flex flex-col overflow-hidden">
      {/* Navigation tabs */}
      <div className="flex items-center gap-6 mb-4 border-b border-[var(--color-border)] pb-0 shrink-0">
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

      <div className="shrink-0 mb-4">
        <h1 className="text-2xl font-bold text-[var(--color-text)] mb-1">
          选择练习病例
        </h1>
        <div className="flex items-center justify-between gap-4">
          <p className="text-sm text-[var(--color-text-secondary)]">
            共 {cases.length} 个病例 · 显示 {filteredCases.length} 个
          </p>
          {/* Search input */}
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索病例标题或主诉..."
            className="px-3 py-1.5 text-sm border border-[var(--color-border)] rounded-lg
                       bg-white w-52 focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20
                       focus:border-[var(--color-primary)] transition-all"
          />
        </div>
      </div>

      {/* Scrollable case list */}
      <div className="flex-1 overflow-y-auto">
        {filteredCases.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-sm text-[var(--color-text-secondary)]">
            {search ? '没有匹配的病例，试试其他关键词' : '暂无可用病例'}
          </div>
        ) : (
          <div className="flex flex-col gap-3 pb-4">
            {filteredCases.map((c) => (
              <div
                key={c.id}
                onClick={() => creating === null && handleSelect(c)}
                className={`p-4 border border-[var(--color-border)] rounded-xl
                            transition-colors cursor-pointer
                            hover:border-blue-200 hover:bg-blue-50/50 hover:shadow-sm
                            ${creating === c.id ? 'opacity-60 pointer-events-none' : ''}`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-2 min-w-0">
                    {c.case_number ? (
                      <span className="text-xs font-mono font-medium text-[var(--color-primary)] bg-[var(--color-primary)]/8 px-1.5 py-0.5 rounded shrink-0">
                        #{c.case_number}
                      </span>
                    ) : null}
                    <h3 className="text-base font-semibold text-[var(--color-text)] m-0 truncate">
                      {c.title}
                    </h3>
                  </div>
                  <DifficultyBadge difficulty={c.difficulty} />
                </div>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1.5 line-clamp-2">
                  {c.chief_complaint || '（病例详情请点击查看）'}
                </p>
                <div className="flex gap-3 mt-2 text-xs text-[var(--color-text-secondary)]">
                  <span>🏥 {c.department}</span>
                  <span>{c.visit_type}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
