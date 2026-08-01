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

  const inputClass = `w-full px-3 py-2 border border-[var(--color-border)] rounded-lg text-sm
                       focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent
                       transition-shadow`;

  const labelClass = 'text-sm font-medium text-[var(--color-text)] block mb-1.5';

  return (
    <form onSubmit={handleSubmit} className="p-5 space-y-3">
      <h3 className="text-base font-semibold text-[var(--color-text)] m-0">
        📋 提交诊断报告
      </h3>

      <div>
        <label className={labelClass}>
          主诊断 <span className="text-[var(--color-error)]">*</span>
        </label>
        <input
          className={inputClass}
          value={form.primary_diagnosis}
          onChange={(e) => update('primary_diagnosis', e.target.value)}
          placeholder="例如：右下第一磨牙慢性牙髓炎"
          required
        />
      </div>

      <div>
        <label className={labelClass}>鉴别诊断</label>
        <input
          className={inputClass}
          value={form.differential_diagnosis}
          onChange={(e) => update('differential_diagnosis', e.target.value)}
          placeholder="列出需要考虑的其他可能诊断"
        />
      </div>

      <div>
        <label className={labelClass}>诊断依据</label>
        <textarea
          className={`${inputClass} min-h-[80px] resize-none`}
          value={form.evidence}
          onChange={(e) => update('evidence', e.target.value)}
          placeholder="根据问诊获得的信息，说明你的诊断依据"
        />
      </div>

      <div>
        <label className={labelClass}>建议检查</label>
        <input
          className={inputClass}
          value={form.suggested_exams}
          onChange={(e) => update('suggested_exams', e.target.value)}
          placeholder="例如：X光片、CBCT、冷热诊"
        />
      </div>

      <div>
        <label className={labelClass}>治疗方案</label>
        <textarea
          className={`${inputClass} min-h-[60px] resize-none`}
          value={form.treatment_plan}
          onChange={(e) => update('treatment_plan', e.target.value)}
          placeholder="急症处理 + 根治方案 + 修复方案"
        />
      </div>

      <button
        type="submit"
        disabled={loading || !form.primary_diagnosis.trim()}
        className="w-full py-3 rounded-lg font-medium text-sm transition-all active:scale-[0.98]
                   bg-[var(--color-success)] text-white hover:opacity-90
                   disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
      >
        {loading ? '评估中...' : '提交诊断并查看评估'}
      </button>
    </form>
  );
}
