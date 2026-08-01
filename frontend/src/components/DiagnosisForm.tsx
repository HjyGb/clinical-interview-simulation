import { useState } from 'react';
import type { DiagnosisSubmit } from '../types';

interface Props {
  onSubmit: (diagnosis: DiagnosisSubmit) => void;
  loading: boolean;
}

export default function DiagnosisForm({ onSubmit, loading }: Props) {
  const [form, setForm] = useState<DiagnosisSubmit>({
    primary_diagnosis: '',
    differential_diagnosis: '',
    evidence: '',
    suggested_exams: '',
    treatment_plan: '',
  });

  const update = (field: keyof DiagnosisSubmit, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.primary_diagnosis.trim()) return;
    onSubmit(form);
  };

  const fieldStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    border: '1px solid #d9d9d9',
    borderRadius: 6,
    fontSize: 14,
    marginBottom: 12,
    boxSizing: 'border-box',
  };

  return (
    <form onSubmit={handleSubmit} style={{ padding: 20 }}>
      <h3 style={{ marginTop: 0 }}>📋 提交诊断报告</h3>

      <label style={{ fontSize: 14, fontWeight: 500 }}>主诊断 *</label>
      <input
        style={fieldStyle}
        value={form.primary_diagnosis}
        onChange={(e) => update('primary_diagnosis', e.target.value)}
        placeholder="例如：右下第一磨牙慢性牙髓炎"
        required
      />

      <label style={{ fontSize: 14, fontWeight: 500 }}>鉴别诊断</label>
      <input
        style={fieldStyle}
        value={form.differential_diagnosis}
        onChange={(e) => update('differential_diagnosis', e.target.value)}
        placeholder="列出需要考虑的其他可能诊断"
      />

      <label style={{ fontSize: 14, fontWeight: 500 }}>诊断依据</label>
      <textarea
        style={{ ...fieldStyle, minHeight: 80, resize: 'vertical' }}
        value={form.evidence}
        onChange={(e) => update('evidence', e.target.value)}
        placeholder="根据问诊获得的信息，说明你的诊断依据"
      />

      <label style={{ fontSize: 14, fontWeight: 500 }}>建议检查</label>
      <input
        style={fieldStyle}
        value={form.suggested_exams}
        onChange={(e) => update('suggested_exams', e.target.value)}
        placeholder="例如：X光片、CBCT、冷热诊"
      />

      <label style={{ fontSize: 14, fontWeight: 500 }}>治疗方案</label>
      <textarea
        style={{ ...fieldStyle, minHeight: 60, resize: 'vertical' }}
        value={form.treatment_plan}
        onChange={(e) => update('treatment_plan', e.target.value)}
        placeholder="急症处理 + 根治方案 + 修复方案"
      />

      <button
        type="submit"
        disabled={loading || !form.primary_diagnosis.trim()}
        style={{
          width: '100%',
          padding: '12px',
          background: loading ? '#d9d9d9' : '#52c41a',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          fontSize: 16,
          cursor: loading ? 'not-allowed' : 'pointer',
          fontWeight: 500,
        }}
      >
        {loading ? '评估中...' : '提交诊断并查看评估'}
      </button>
    </form>
  );
}
