import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { sendMessage, endSession } from '../api/sessions';
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
  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [store.messages]);

  const handleSend = useCallback(async (content: string) => {
    if (store.isStreaming || store.isEnded) return;

    // Add student message optimistically
    store.addMessage({
      id: Date.now(),
      session_id: sessionId,
      role: 'student',
      content,
      round_num: store.currentRound + 1,
      created_at: new Date().toISOString(),
    });

    store.setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

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
            case 'done':
              store.setStreaming(false);
              // Freeze the streaming message by replacing its id
              store.addMessage({
                id: Date.now(),
                session_id: sessionId,
                role: 'patient',
                content: '',
                round_num: store.currentRound + 1,
                created_at: new Date().toISOString(),
              });
              break;
            case 'error':
              store.setStreaming(false);
              alert(data.message as string);
              break;
          }
        },
        controller.signal,
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        store.setStreaming(false);
        alert(`发送失败：${(e as Error).message}`);
      }
    }
  }, [sessionId, store]);

  const handleDiagnosisSubmit = async (diagnosis: DiagnosisSubmit) => {
    setAssessing(true);
    try {
      const result = await submitAssessment(sessionId, diagnosis);
      navigate(`/assessment/${sessionId}`, { state: { result } });
    } catch (e) {
      alert(`评估失败：${(e as Error).message}`);
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
      alert(`结束会话失败：${(e as Error).message}`);
    }
  };

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
            <button
              onClick={handleEndSession}
              style={{
                padding: '6px 14px',
                background: '#ff4d4f',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              结束问诊
            </button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: '20px',
      }}>
        {store.messages.length === 0 && (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 60 }}>
            <p style={{ fontSize: 16 }}>AI 患者正在准备开场白...</p>
            <p style={{ fontSize: 13 }}>患者会首先描述自己的不适，然后你可以开始提问。</p>
          </div>
        )}
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

      {/* Diagnosis form overlay or input */}
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
            store.isEnded ? '问诊已结束' :
            '输入你的问诊问题，按 Enter 发送'
          }
        />
      )}
    </div>
  );
}
