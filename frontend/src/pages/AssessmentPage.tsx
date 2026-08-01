import { useEffect, useState } from 'react';
import { useLocation, useParams, useNavigate } from 'react-router-dom';
import { getAssessment } from '../api/assessments';
import ScoreCard from '../components/ScoreCard';
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
      <div style={{ textAlign: 'center', padding: 80, color: '#999' }}>
        <p style={{ fontSize: 18 }}>正在生成评估报告...</p>
        <p style={{ fontSize: 14 }}>AI 正在分析你的问诊表现</p>
      </div>
    );
  }

  if (!result) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <p>无法加载评估结果</p>
        <button onClick={() => navigate('/cases')} style={{
          marginTop: 16,
          padding: '10px 24px',
          background: '#1677ff',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
        }}>
          返回病例列表
        </button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>📊 评估报告</h1>
        <p style={{ color: '#999', marginTop: 4 }}>
          综合评分：{((result.diagnostic.total_score + result.communication.total_score) / 2).toFixed(1)}/100
        </p>
      </div>

      <ScoreCard title="🏥 诊断能力评估 (Station 4 标准)" block={result.diagnostic} />
      <ScoreCard title="💬 沟通能力评估 (MAAS-Global 标准)" block={result.communication} />

      <div style={{ textAlign: 'center', marginTop: 24 }}>
        <button
          onClick={() => navigate('/cases')}
          style={{
            padding: '12px 32px',
            background: '#1677ff',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 16,
            cursor: 'pointer',
          }}
        >
          练习其他病例
        </button>
      </div>
    </div>
  );
}
