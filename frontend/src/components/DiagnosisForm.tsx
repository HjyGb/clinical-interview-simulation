import { useState } from 'react';
import type { DiagnosisSubmit } from '../types';

interface Props {
  onSubmit: (diagnosis: DiagnosisSubmit) => void;
  loading: boolean;
}

// 答卷五项，一一对应 R06–R10。占位提示刻意对齐锚点的要求
// （如 R06 要"部位 + 确定性"、R08 要"区分依据"），不是随便写的例子。
const FIELDS: {
  key: keyof DiagnosisSubmit;
  label: string;
  placeholder: string;
  required?: boolean;
  textarea?: boolean;
  hint?: string;
}[] = [
  {
    key: 'primary_diagnosis',
    label: '① 主诊断',
    placeholder: '例如：36深龋；36可复性牙髓炎',
    required: true,
    hint: '写清部位（哪颗牙/哪个区域）与确定程度',
  },
  {
    key: 'diagnosis_reason',
    label: '② 诊断理由',
    placeholder: '用你实际问到的症状与拿到的检查结果说明推理链，而不是只报病名',
    textarea: true,
    hint: '要能看出你是从哪些证据推到结论的',
  },
  {
    key: 'differential_diagnosis',
    label: '③ 鉴别诊断',
    placeholder: '例如：症状性不可复性牙髓炎——本例缺少持续冷痛、自发和夜间痛',
    textarea: true,
    hint: '列出关键鉴别，并说明为什么排除或还需什么资料',
  },
  {
    key: 'immediate_plan',
    label: '④ 近期处理',
    placeholder: '本次当下要做什么（安全优先）',
    textarea: true,
  },
  {
    key: 'staged_plan',
    label: '⑤ 阶段计划与复评',
    placeholder: '确定性处理、条件性/替代路径、以及什么时候复评',
    textarea: true,
  },
];

export default function DiagnosisForm({ onSubmit, loading }: Props) {
  const [form, setForm] = useState<DiagnosisSubmit>({
    primary_diagnosis: '',
    diagnosis_reason: '',
    differential_diagnosis: '',
    immediate_plan: '',
    staged_plan: '',
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
    <form onSubmit={handleSubmit} className="p-5 space-y-4">
      <div>
        <h3 className="text-base font-semibold text-[var(--color-text)] m-0">
          📋 提交诊断报告
        </h3>
        <p className="text-xs text-[var(--color-text-secondary)] mt-1">
          共五项。第②③项尤其要写清 reasoning——只写病名拿不到分。
        </p>
      </div>

      {FIELDS.map((f) => (
        <div key={f.key}>
          <label className={labelClass} htmlFor={f.key}>
            {f.label}
            {f.required && <span className="text-[var(--color-error)]"> *</span>}
          </label>
          {f.textarea ? (
            <textarea
              id={f.key}
              className={`${inputClass} min-h-[72px] resize-none`}
              value={form[f.key]}
              onChange={(e) => update(f.key, e.target.value)}
              placeholder={f.placeholder}
            />
          ) : (
            <input
              id={f.key}
              className={inputClass}
              value={form[f.key]}
              onChange={(e) => update(f.key, e.target.value)}
              placeholder={f.placeholder}
              required={f.required}
            />
          )}
          {f.hint && (
            <p className="text-[11px] text-[var(--color-text-secondary)] mt-1">{f.hint}</p>
          )}
        </div>
      ))}

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
