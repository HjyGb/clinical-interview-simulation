import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { getMessages, sendMessage, endSession } from '../api/sessions';
import { submitAssessment } from '../api/assessments';
import ChatBubble from '../components/ChatBubble';
import ChatInput from '../components/ChatInput';
import DiagnosisForm from '../components/DiagnosisForm';
import { useInterviewStore } from '../stores/interviewStore';
import type { DiagnosisSubmit } from '../types';

export default function InterviewPage() {
  const { id } = useParams<{ id: string }>();
  const sessionId = Number(id);
  const navigate = useNavigate();
  const store = useInterviewStore();
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [assessing, setAssessing] = useState(false);
  const [roundsLeft, setRoundsLeft] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Load messages on mount
  useEffect(() => {
    let cancelled = false;
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    getMessages(sessionId)
      .then((res) => {
        if (cancelled) return;
        store.reset();
        for (const msg of res.messages) {
          store.addMessage(msg);
        }
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError((err as Error).message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [sessionId, navigate, store]);

  // Auto-scroll on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [store.messages]);

  const handleSend = useCallback(async (content: string) => {
    if (store.isStreaming || store.isEnded) return;

    // Add student message to state
    store.addMessage({
      id: Date.now(),
      session_id: sessionId,
      role: 'student' as const,
      content,
      round_num: store.currentRound + 1,
      created_at: new Date().toISOString(),
    });

    store.setStreaming(true);

    try {
      await sendMessage(
        sessionId,
        content,
        (event, data) => {
          switch (event) {
            case 'token':
              store.appendToken(data.token as string);
              break;
            case 'limit_warning':
              setRoundsLeft(data.remaining_rounds as number);
              break;
            case 'error':
              store.setStreaming(false);
              setError(data.message as string);
              break;
          }
        },
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        store.setStreaming(false);
        setError(`发送失败：${(e as Error).message}`);
      }
    }
    // streaming stays true until next explicit action or error
    store.setStreaming(false);
  }, [sessionId, store]);

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
      store.setEnded();
      setShowDiagnosis(true);
    } catch (e) {
      setError(`结束会话失败：${(e as Error).message}`);
    }
  };

  // ── Loading State ──
  if (loading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        color: '#999',
      }}>
        <p style={{ fontSize: 18 }}>🤒 AI 患者正在准备...</p>
        <p style={{ fontSize: 14 }}>正在生成开场白，请稍候</p>
      </div>
    );
  }

  // ── Error State ──
  if (error && store.messages.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        color: '#ff4d4f',
      }}>
        <p style={{ fontSize: 18 }}>❌ 加载失败</p>
        <p style={{ fontSize: 14, color: '#666' }}>{error}</p>
        <button onClick={() => navigate('/cases')} style={{
          marginTop: 16,
          padding: '10px 24px',
          background: '#1677ff',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          cursor: 'pointer',
        }}>返回病例列表</button>
      </div>
    );
  }

  // ── Main Interview UI ──
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      maxWidth: 720,
      margin: '0 auto',
      background: '#fafafa',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px',
        background: '#fff',
        borderBottom: '1px solid #e8e8e8',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <h3 style={{ margin: 0 }}>🩺 AI 患者问诊</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {roundsLeft !== null && roundsLeft <= 2 && (
            <span style={{ color: '#ff4d4f', fontSize: 13 }}>
              ⚠️ 剩余 {roundsLeft} 轮
            </span>
          )}
          <span style={{ fontSize: 13, color: '#999' }}>
            第 {store.currentRound}/{store.maxRounds} 轮
          </span>
          {!store.isEnded && (
            <button onClick={handleEndSession} style={{
              padding: '6px 14px',
              background: '#ff4d4f',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              fontSize: 13,
              cursor: 'pointer',
            }}>结束问诊</button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '8px 16px',
          background: '#fff2f0',
          borderBottom: '1px solid #ffccc7',
          color: '#ff4d4f',
          fontSize: 13,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{
            background: 'none',
            border: 'none',
            color: '#ff4d4f',
            cursor: 'pointer',
            fontSize: 14,
          }}>✕</button>
        </div>
      )}

      {/* Messages area */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px' }}>
        {store.messages.map((msg, i) => (
          <ChatBubble
            key={msg.id === -1 ? `stream-${i}` : msg.id}
            role={msg.role}
            content={msg.content}
            isStreaming={msg.id === -1 && store.isStreaming}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Diagnosis or input */}
      {showDiagnosis ? (
        <div style={{
          borderTop: '1px solid #e8e8e8',
          background: '#fff',
          maxHeight: '60vh',
          overflow: 'auto',
        }}>
          <DiagnosisForm onSubmit={handleDiagnosisSubmit} loading={assessing} />
        </div>
      ) : (
        <ChatInput
          onSend={handleSend}
          disabled={store.isStreaming || store.isEnded}
          placeholder={
            store.isStreaming ? '患者正在输入...' :
            store.isEnded ? '问诊已结束 — 点击上方"结束问诊"提交诊断' :
            '输入你的问诊问题，按 Enter 发送'
          }
        />
      )}
    </div>
  );
}
