import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, getMessages } from '../api/sessions';
import { getAssessment } from '../api/assessments';
import ChatBubble from '../components/ChatBubble';
import ScoreCard from '../components/ScoreCard';
import DifficultyBadge from '../components/ui/DifficultyBadge';
import StatusBadge from '../components/ui/StatusBadge';
import LoadingDots from '../components/ui/LoadingDots';
import Modal from '../components/ui/Modal';
import ProgressBar from '../components/ui/ProgressBar';
import type { SessionListItem, ChatMessage, AssessmentResult } from '../types';

function FieldDisplay({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-[10px] font-medium text-[var(--color-text-secondary)]">
        {label}
      </span>
      <p className="text-xs text-[var(--color-text)] mt-0.5">{value}</p>
    </div>
  );
}

function formatDate(isoStr: string | null): string {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function formatDateTime(isoStr: string | null): string {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [msgsLoading, setMsgsLoading] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResult | null>(null);
  const [assessLoading, setAssessLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  // Fetch session list on mount
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }
    listSessions()
      .then((res) => {
        setSessions(res.sessions);
        if (res.sessions.length > 0) setSelectedId(res.sessions[0].id);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [navigate]);

  // Fetch messages + assessment when selected session changes
  const loadSessionData = useCallback((id: number) => {
    setMessages([]);
    setAssessment(null);
    setMsgsLoading(true);
    setAssessLoading(true);

    getMessages(id)
      .then((res) => setMessages(res.messages))
      .catch(console.error)
      .finally(() => setMsgsLoading(false));

    getAssessment(id)
      .then(setAssessment)
      .catch(() => setAssessment(null))
      .finally(() => setAssessLoading(false));
  }, []);

  useEffect(() => {
    if (selectedId) loadSessionData(selectedId);
  }, [selectedId, loadSessionData]);

  const handleSelectSession = (id: number) => setSelectedId(id);

  // Find the currently selected session
  const selectedSession = sessions.find((s) => s.id === selectedId) || null;

  // ── Full-page loading ──
  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <LoadingDots text="加载历史记录中..." />
      </div>
    );
  }

  // ── Error state ──
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-lg text-[var(--color-error)]">❌ 加载失败</p>
        <p className="text-sm text-[var(--color-text-secondary)]">{error}</p>
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

  // ── Empty state ──
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-lg text-[var(--color-text-secondary)]">📋 暂无练习记录</p>
        <button
          onClick={() => navigate('/cases')}
          className="px-6 py-2.5 rounded-lg font-medium text-sm transition-all
                     bg-[var(--color-primary)] text-white hover:opacity-90 active:scale-[0.98]"
        >
          去新建练习
        </button>
      </div>
    );
  }

  // ── Main 3-panel layout ──
  return (
    <div className="h-screen flex flex-col bg-[var(--color-bg)] overflow-hidden">
      {/* Top navigation bar */}
      <header className="h-14 bg-white border-b border-[var(--color-border)] flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-bold text-[var(--color-text)] m-0">
            历史练习记录
          </h1>
          <nav className="flex gap-4">
            <button
              onClick={() => navigate('/cases')}
              className="text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)]
                         transition-colors pb-0.5"
            >
              病例列表
            </button>
            <button
              onClick={() => navigate('/history')}
              className="text-sm font-medium text-[var(--color-primary)]
                         border-b-2 border-[var(--color-primary)] pb-0.5"
            >
              历史记录
            </button>
          </nav>
        </div>
        <button
          onClick={() => navigate('/cases')}
          className="px-4 py-1.5 rounded-lg text-sm font-medium transition-all
                     bg-[var(--color-primary)] text-white hover:opacity-90 active:scale-[0.98]"
        >
          + 新建练习
        </button>
      </header>

      {/* 3-panel body */}
      <div
        className="flex-1 grid overflow-hidden"
        style={{ gridTemplateColumns: '1fr 3fr 2fr' }}
      >
        {/* ══ Left: Session List ══ */}
        <div className="bg-white flex flex-col border-r border-[var(--color-border)]">
          <div className="px-4 py-3 border-b border-[var(--color-border)] shrink-0">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">
              练习记录
            </h2>
            <p className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
              共 {sessions.length} 条
            </p>
          </div>
          <div className="flex-1 overflow-y-auto">
            {sessions.map((s) => {
              const isSelected = s.id === selectedId;
              let statusLabel = s.status;
              if (s.has_assessment) statusLabel = 'evaluated';
              else if (s.status === 'ended') statusLabel = 'ended';
              else statusLabel = s.status;

              return (
                <div
                  key={s.id}
                  onClick={() => handleSelectSession(s.id)}
                  className={`px-4 py-3 border-b border-[var(--color-border)] cursor-pointer
                              transition-colors
                              ${isSelected
                                ? 'bg-[var(--color-primary-light)] border-l-2 border-l-[var(--color-primary)]'
                                : 'hover:bg-gray-50 border-l-2 border-l-transparent'
                              }`}
                >
                  <div className="flex justify-between items-start gap-2">
                    <p className="text-sm font-medium text-[var(--color-text)] truncate leading-snug">
                      {s.case_title}
                    </p>
                    <StatusBadge status={statusLabel} />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-[var(--color-text-secondary)]">
                      {s.case_department}
                    </span>
                    <DifficultyBadge difficulty={s.case_difficulty} />
                  </div>
                  <div className="flex justify-between items-center mt-1.5">
                    <span className="text-[10px] text-[var(--color-text-secondary)]">
                      {formatDate(s.started_at)}
                    </span>
                    <span className="text-[10px] text-[var(--color-text-secondary)]">
                      {s.max_rounds} 轮
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ══ Center: Read-only Chat ══ */}
        <div className="bg-white flex flex-col border-r border-[var(--color-border)]">
          <div className="px-4 py-3 border-b border-[var(--color-border)] shrink-0 flex items-center gap-3">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">
              对话记录
            </h2>
            {msgsLoading && <LoadingDots text="" />}
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4">
            {!selectedSession ? (
              <div className="flex items-center justify-center h-full text-sm text-[var(--color-text-secondary)]">
                👈 请从左侧选择一个练习记录
              </div>
            ) : messages.length === 0 && !msgsLoading ? (
              <div className="flex items-center justify-center h-full text-sm text-[var(--color-text-secondary)]">
                暂无对话记录
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <ChatBubble
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    isStreaming={false}
                  />
                ))}
                {selectedSession && (
                  <p className="text-center text-xs text-[var(--color-text-secondary)] py-3 border-t border-[var(--color-border)] mt-2">
                    共 {messages.length} 条消息 · 开始于 {formatDateTime(selectedSession.started_at)}
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* ══ Right: Diagnosis + Assessment ══ */}
        <div className="bg-white flex flex-col">
          <div className="px-4 py-3 border-b border-[var(--color-border)] shrink-0">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">
              诊断与评估
            </h2>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {!selectedSession ? (
              <p className="text-sm text-[var(--color-text-secondary)]">
                请选择一个练习记录
              </p>
            ) : (
              <>
                {/* Student's diagnosis report */}
                <div>
                  <h3 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide mb-2">
                    📋 学生诊断报告
                  </h3>
                  {assessment?.student_report ? (
                    <div className="space-y-2 bg-gray-50 rounded-lg p-3">
                      <FieldDisplay label="主诊断" value={assessment.student_report.primary_diagnosis} />
                      <FieldDisplay label="鉴别诊断" value={assessment.student_report.differential_diagnosis} />
                      <FieldDisplay label="诊断依据" value={assessment.student_report.evidence} />
                      <FieldDisplay label="建议检查" value={assessment.student_report.suggested_exams} />
                      <FieldDisplay label="治疗方案" value={assessment.student_report.treatment_plan} />
                    </div>
                  ) : (
                    <p className="text-xs text-[var(--color-text-secondary)] bg-gray-50 rounded-lg p-3">
                      {assessLoading ? '加载中...' : '未提交诊断或评估未完成'}
                    </p>
                  )}
                </div>

                {/* Assessment summary */}
                {assessment && (
                  <div>
                    <h3 className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide mb-2">
                      📊 评估概览
                    </h3>
                    <div className="bg-gray-50 rounded-lg p-3 space-y-3">
                      <div className="text-center">
                        <span className="text-2xl font-bold text-[var(--color-primary)]">
                          {((assessment.diagnostic.total_score + assessment.communication.total_score) / 2).toFixed(1)}
                        </span>
                        <span className="text-xs text-[var(--color-text-secondary)] ml-1">
                          综合评分
                        </span>
                      </div>
                      <div>
                        <div className="flex justify-between text-[10px] text-[var(--color-text-secondary)] mb-0.5">
                          <span>诊断能力</span>
                          <span>{assessment.diagnostic.total_score}/{assessment.diagnostic.max_score}</span>
                        </div>
                        <ProgressBar value={assessment.diagnostic.total_score} max={assessment.diagnostic.max_score} size="sm" />
                      </div>
                      <div>
                        <div className="flex justify-between text-[10px] text-[var(--color-text-secondary)] mb-0.5">
                          <span>沟通能力</span>
                          <span>{assessment.communication.total_score}/{assessment.communication.max_score}</span>
                        </div>
                        <ProgressBar value={assessment.communication.total_score} max={assessment.communication.max_score} size="sm" />
                      </div>
                    </div>
                  </div>
                )}

                {/* "查看评估详情" button */}
                {assessment && (
                  <button
                    onClick={() => setShowModal(true)}
                    className="w-full py-2 rounded-lg border border-[var(--color-primary)]
                               text-[var(--color-primary)] text-sm font-medium
                               hover:bg-[var(--color-primary-light)] transition-colors"
                  >
                    查看评估详情
                  </button>
                )}

                {!assessment && !assessLoading && selectedSession && selectedSession.status === 'ended' && (
                  <p className="text-xs text-[var(--color-text-secondary)] bg-gray-50 rounded-lg p-3 text-center">
                    该会话尚未提交评估
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Modal: full assessment details */}
      {showModal && assessment && (
        <Modal
          title="评估详情"
          onClose={() => setShowModal(false)}
          maxWidth="max-w-2xl"
        >
          <div className="space-y-6">
            <ScoreCard title="🏥 诊断能力评估 (Station 4 标准)" block={assessment.diagnostic} />
            <ScoreCard title="💬 沟通能力评估 (MAAS-Global 标准)" block={assessment.communication} />
            {selectedSession && (
              <p className="text-xs text-[var(--color-text-secondary)] text-center">
                病例：{selectedSession.case_title} · {formatDate(selectedSession.started_at)}
              </p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
