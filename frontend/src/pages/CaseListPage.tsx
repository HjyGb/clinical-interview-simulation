import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listCases } from '../api/cases';
import { createSession } from '../api/sessions';
import { useInterviewStore } from '../stores/interviewStore';
import type { CaseSummary } from '../types';

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: '#52c41a',
  intermediate: '#faad14',
  advanced: '#ff4d4f',
};

const DIFFICULTY_LABELS: Record<string, string> = {
  beginner: '初级',
  intermediate: '中级',
  advanced: '高级',
};

export default function CaseListPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState<number | null>(null);
  const navigate = useNavigate();
  const setSession = useInterviewStore((s) => s.setSession);

  useEffect(() => {
    listCases()
      .then((res) => setCases(res.cases))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

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
      <div style={{ padding: 60, textAlign: 'center', color: '#999' }}>
        加载病例列表中...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 40 }}>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>📋 选择练习病例</h1>
      <p style={{ color: '#999', marginBottom: 24 }}>
        选择一个病例开始 AI 问诊练习。每个病例有不同的难度和疾病类型。
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {cases.map((c) => (
          <div
            key={c.id}
            style={{
              padding: 20,
              border: '1px solid #e8e8e8',
              borderRadius: 12,
              cursor: creating === c.id ? 'wait' : 'pointer',
              transition: 'box-shadow 0.2s',
              opacity: creating === c.id ? 0.6 : 1,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.08)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = 'none';
            }}
            onClick={() => creating === null && handleSelect(c)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
              <h3 style={{ margin: 0, fontSize: 17 }}>{c.title}</h3>
              <span style={{
                padding: '2px 10px',
                borderRadius: 12,
                fontSize: 12,
                fontWeight: 500,
                background: DIFFICULTY_COLORS[c.difficulty] + '20',
                color: DIFFICULTY_COLORS[c.difficulty],
              }}>
                {DIFFICULTY_LABELS[c.difficulty] || c.difficulty}
              </span>
            </div>
            <p style={{ color: '#666', fontSize: 14, marginTop: 8 }}>
              {c.chief_complaint || '（病例详情请点击查看）'}
            </p>
            <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: 13, color: '#999' }}>
              <span>🏥 {c.department}</span>
              <span>{c.visit_type}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
