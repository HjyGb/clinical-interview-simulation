import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { getMessages, getSession, sendMessage, endSession } from '../api/sessions';
import { submitAssessment } from '../api/assessments';
import ChatBubble from '../components/ChatBubble';
import ChatInput from '../components/ChatInput';
import DiagnosisForm from '../components/DiagnosisForm';
import Alert from '../components/ui/Alert';
import LoadingDots from '../components/ui/LoadingDots';
import { useInterviewStore } from '../stores/interviewStore';
import type { DiagnosisSubmit } from '../types';

export default function InterviewPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const navigate = useNavigate();

  // 逐字段订阅。**不要** `const store = useInterviewStore()`——
  // 那会订阅整个 store，每次状态变化 store 的引用都变，挂载 effect 就会跟着重跑，
  // 结果是每发一条消息就把全部历史重新拉一遍（并持续打断滚动）。
  const messages = useInterviewStore((s) => s.messages);
  const currentRound = useInterviewStore((s) => s.currentRound);
  const maxRounds = useInterviewStore((s) => s.maxRounds);
  const isStreaming = useInterviewStore((s) => s.isStreaming);
  const isEnded = useInterviewStore((s) => s.isEnded);

  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [roundsLeft, setRoundsLeft] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load session + messages on mount
  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    // 会话信息与消息一起取：max_rounds 只能来自后端，缺了就会显示成占位值。
    Promise.all([getSession(sessionId), getMessages(sessionId)])
      .then(([sess, res]) => {
        if (cancelled) return;
        const s = useInterviewStore.getState();
        s.setSession(sessionId, sess.max_rounds);
        for (const msg of res.messages) {
          s.addMessage(msg);
        }
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError((err as Error).message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [sessionId, navigate]);

  // 只在用户本来就在底部时才自动跟随。否则流式期间每来一个 token 都会
  // 把他手动向上翻看历史的动作拽回底部——看起来就像"划不上去"。
  const scrollBoxRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = scrollBoxRef.current;
    if (!box) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    if (nearBottom) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  const handleSend = useCallback(async (content: string) => {
    if (isStreaming || isEnded) return;

    setError(null);
    useInterviewStore.getState().addMessage({
      id: Date.now(),
      session_id: sessionId,
      role: 'student' as const,
      content,
      round_num: currentRound + 1,
      created_at: new Date().toISOString(),
    });

    useInterviewStore.getState().setStreaming(true);

    try {
      await sendMessage(
        sessionId,
        content,
        (event, data) => {
          switch (event) {
            case 'token':
              useInterviewStore.getState().appendToken(data.token as string);
              break;
            case 'exam':
              useInterviewStore.getState().appendExam(data.content as string);
              break;
            case 'data_gap':
              useInterviewStore.getState().appendSystem(data.message as string);
              break;
            case 'limit_warning':
              setRoundsLeft(data.remaining_rounds as number);
              break;
            case 'error':
              useInterviewStore.getState().setStreaming(false);
              setError(data.message as string);
              break;
          }
        },
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        useInterviewStore.getState().setStreaming(false);
        setError(`发送失败：${(e as Error).message}`);
      }
    }
    useInterviewStore.getState().setStreaming(false);
  }, [sessionId, currentRound]);

  const handleDiagnosisSubmit = async (diagnosis: DiagnosisSubmit) => {
    setAssessing(true);
    try {
      const result = await submitAssessment(sessionId, diagnosis);
      navigate(`/assessment/${sessionId}`, { state: { result } });
    } catch (e) {
      setError(`评估失败：${(e as Error).message}`);
    } finally {
      setAssessing(false);
    }
  };

  const handleEndSession = async () => {
    try {
      await endSession(sessionId);
      useInterviewStore.getState().setEnded();
      setShowDiagnosis(true);
    } catch (e) {
      setError(`结束会话失败：${(e as Error).message}`);
    }
  };

  // ── Loading State ──
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3 text-[var(--color-text-secondary)]">
        <span className="text-4xl">🤒</span>
        <p className="text-lg font-medium">AI 患者正在准备...</p>
        <LoadingDots text="正在生成开场白，请稍候" />
      </div>
    );
  }

  // ── Error State (no messages) ──
  if (error && messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-2">
        <p className="text-lg text-[var(--color-error)]">❌ 加载失败</p>
        <p className="text-sm text-[var(--color-text-secondary)]">{error}</p>
        <button
          onClick={() => navigate('/cases')}
          className="mt-4 px-6 py-2.5 rounded-lg font-medium text-sm transition-all
                     bg-[var(--color-primary)] text-white hover:opacity-90 active:scale-[0.98]"
        >
          返回病例列表
        </button>
      </div>
    );
  }

  // ── Main Interview UI ──
  return (
    <div className="flex flex-col h-screen max-w-[720px] mx-auto bg-[var(--color-bg)] overflow-hidden">
      {/* Header */}
      <header className="flex justify-between items-center px-5 py-3 bg-white border-b border-[var(--color-border)] shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/cases')}
            className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]
                       hover:text-[var(--color-text)] transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>返回</span>
          </button>
          <h3 className="text-base font-semibold text-[var(--color-text)] m-0">
            🩺 AI 患者问诊
          </h3>
        </div>
        <div className="flex gap-2 items-center">
          {roundsLeft !== null && roundsLeft <= 2 && (
            <span className="text-xs text-[var(--color-error)] font-medium">
              ⚠️ 剩余 {roundsLeft} 轮
            </span>
          )}
          <span className="text-xs text-[var(--color-text-secondary)]">
            第 {currentRound}/{maxRounds || '—'} 轮
          </span>
          {!isEnded && (
            <button
              onClick={handleEndSession}
              className="px-3.5 py-1.5 rounded-md text-xs font-medium text-white
                         bg-[var(--color-error)] hover:opacity-90 active:scale-[0.98] transition-all"
            >
              结束问诊
            </button>
          )}
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <Alert type="error" className="rounded-none border-l-0 border-b border-red-200 flex justify-between items-center">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-sm opacity-70 hover:opacity-100 ml-2"
          >
            ✕
          </button>
        </Alert>
      )}

      {/* Messages area */}
      <div ref={scrollBoxRef} className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
        {messages.map((msg, i) => (
          <ChatBubble
            key={msg.id === -1 ? `stream-${i}` : msg.id}
            role={msg.role}
            content={msg.content}
            isStreaming={msg.id === -1 && isStreaming}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Round warning */}
      {!isEnded && roundsLeft !== null && roundsLeft <= 2 && (
        <Alert type="warning" className="rounded-none border-l-0 text-center">
          已达到最大问诊轮次 ({maxRounds})，请提交病例诊断记录。
        </Alert>
      )}

      {/* Diagnosis or input */}
      {showDiagnosis ? (
        <div className="border-t border-[var(--color-border)] bg-white max-h-[60vh] overflow-y-auto">
          <DiagnosisForm onSubmit={handleDiagnosisSubmit} loading={assessing} />
        </div>
      ) : (
        <ChatInput
          onSend={handleSend}
          disabled={isStreaming || isEnded}
          placeholder={
            isStreaming
              ? '患者正在输入...'
              : isEnded
                ? '问诊已结束 — 点击上方"结束问诊"提交诊断'
                : '输入你的问诊问题，按 Enter 发送'
          }
        />
      )}
    </div>
  );
}
