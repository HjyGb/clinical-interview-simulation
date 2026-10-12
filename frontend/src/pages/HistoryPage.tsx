import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { deleteSession, listSessions, getMessages } from '../api/sessions';
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
  const [deleteTarget, setDeleteTarget] = useState<SessionListItem | null>(null);
  const [deleting, setDeleting] = useState(false);

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

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteSession(deleteTarget.id);
      // Remove from local list
      const updated = sessions.filter((s) => s.id !== deleteTarget.id);
      setSessions(updated);
      // If deleted session was selected, pick another
      if (selectedId === deleteTarget.id) {
        setSelectedId(updated.length > 0 ? updated[0].id : null);
        setMessages([]);
        setAssessment(null);
      }
      setDeleteTarget(null);
    } catch (e) {
      console.error('删除失败:', e);
    } finally {
      setDeleting(false);
    }
  };

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
        className="flex-1 min-h-0 grid overflow-hidden"
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
          <div className="flex-1 min-h-0 overflow-y-auto">
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
                  className={`group px-4 py-3 border-b border-[var(--color-border)] cursor-pointer
                              transition-colors relative
                              ${isSelected
                                ? 'bg-[var(--color-primary-light)] border-l-2 border-l-[var(--color-primary)]'
                                : 'hover:bg-gray-50 border-l-2 border-l-transparent'
                              }`}
                >
                  <div className="flex justify-between items-start gap-2">
                    <p className="text-sm font-medium text-[var(--color-text)] truncate leading-snug pr-5">
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
                  {/* Delete button — visible on hover */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(s);
                    }}
                    title="删除此记录"
                    className="absolute top-2 right-2 w-6 h-6 rounded flex items-center justify-center
                               opacity-0 group-hover:opacity-100 transition-opacity
                               text-[var(--color-text-secondary)] hover:text-red-500 hover:bg-red-50"
                  >
                    🗑️
                  </button>
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
          <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
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
          <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
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
                      <FieldDisplay label="① 主诊断" value={assessment.student_report.primary_diagnosis} />
                      <FieldDisplay label="② 诊断理由" value={assessment.student_report.diagnosis_reason} />
                      <FieldDisplay label="③ 鉴别诊断" value={assessment.student_report.differential_diagnosis} />
                      <FieldDisplay label="④ 近期处理" value={assessment.student_report.immediate_plan} />
                      <FieldDisplay label="⑤ 阶段计划" value={assessment.student_report.staged_plan} />
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
                      {assessment.report?.safety?.requires_review && (
                        <p className="text-[11px] text-red-600 font-medium">
                          ⚠ 有安全标记需人工复核
                        </p>
                      )}
                      <div className="text-center">
                        <span className="text-2xl font-bold text-[var(--color-primary)]">
                          {assessment.raw_total}
                        </span>
                        <span className="text-xs text-[var(--color-text-secondary)] ml-1">
                          / {assessment.report.total.raw_max_counted} 原始分
                        </span>
                      </div>
                      {assessment.report.views.map((v) => {
                        const score = v.groups.reduce((s, g) => s + g.score, 0);
                        const max = v.groups.reduce((s, g) => s + g.max, 0);
                        return (
                          <div key={v.name}>
                            <div className="flex justify-between text-[10px] text-[var(--color-text-secondary)] mb-0.5">
                              <span>{v.name}</span>
                              <span>{score}/{max}</span>
                            </div>
                            <ProgressBar value={score} max={max} size="sm" />
                          </div>
                        );
                      })}
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
            <ScoreCard report={assessment.report} />
            {selectedSession && (
              <p className="text-xs text-[var(--color-text-secondary)] text-center">
                病例：{selectedSession.case_title} · {formatDate(selectedSession.started_at)}
              </p>
            )}
          </div>
        </Modal>
      )}

      {/* Modal: delete confirmation */}
      {deleteTarget && (
        <Modal
          title="确认删除"
          onClose={() => !deleting && setDeleteTarget(null)}
          maxWidth="max-w-sm"
        >
          <div className="space-y-4">
            <p className="text-sm text-[var(--color-text)]">
              确定要删除以下练习记录吗？
            </p>
            <div className="bg-gray-50 rounded-lg p-3 space-y-1">
              <p className="text-sm font-medium text-[var(--color-text)]">
                {deleteTarget.case_title}
              </p>
              <p className="text-xs text-[var(--color-text-secondary)]">
                {deleteTarget.case_department} · {formatDate(deleteTarget.started_at)} · {deleteTarget.max_rounds} 轮
              </p>
            </div>
            <p className="text-xs text-red-500">
              ⚠️ 此操作不可恢复，对话记录和评估结果将被永久删除。
            </p>
            <div className="flex gap-3 justify-end pt-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleting}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-all
                           border border-[var(--color-border)] text-[var(--color-text-secondary)]
                           hover:bg-gray-50 disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 rounded-lg text-sm font-medium transition-all
                           bg-red-500 text-white hover:bg-red-600
                           disabled:opacity-50 active:scale-[0.98]"
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
