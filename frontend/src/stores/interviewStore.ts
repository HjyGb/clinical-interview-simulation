import { create } from 'zustand';
import type { ChatMessage } from '../types';

interface InterviewState {
  sessionId: number | null;
  messages: ChatMessage[];
  currentRound: number;
  maxRounds: number;
  isStreaming: boolean;
  isEnded: boolean;
  setSession: (id: number, maxRounds: number) => void;
  addMessage: (msg: ChatMessage) => void;
  appendToken: (token: string) => void;
  appendExam: (content: string) => void;
  setStreaming: (v: boolean) => void;
  setEnded: () => void;
  reset: () => void;
}

export const useInterviewStore = create<InterviewState>((set, get) => ({
  sessionId: null,
  messages: [],
  currentRound: 0,
  maxRounds: 12,
  isStreaming: false,
  isEnded: false,

  setSession: (id, maxRounds) =>
    set({ sessionId: id, maxRounds, messages: [], currentRound: 0, isEnded: false }),

  // 一轮 = 学生一次发言，与后端 _student_turn_count 的口径一致。
  // （原来按 patient 消息计数，加了检查结果这种额外回复行之后会对不上。）
  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
      currentRound: msg.role === 'student' ? s.currentRound + 1 : s.currentRound,
    })),

  appendToken: (token) => {
    const msgs = get().messages;
    const last = msgs[msgs.length - 1];
    if (last && last.role === 'patient' && last.id === -1) {
      // Append to streaming message
      set({
        messages: [
          ...msgs.slice(0, -1),
          { ...last, content: last.content + token },
        ],
      });
    } else {
      // Create new streaming message
      const streamMsg: ChatMessage = {
        id: -1,
        session_id: get().sessionId || 0,
        role: 'patient',
        content: token,
        round_num: get().currentRound,
        created_at: new Date().toISOString(),
      };
      set({ messages: [...msgs, streamMsg] });
    }
  },

  // 检查结果是整段文本，不流式
  appendExam: (content) =>
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: -1,
          session_id: s.sessionId || 0,
          role: 'exam',
          content,
          round_num: s.currentRound,
          created_at: new Date().toISOString(),
        },
      ],
    })),

  setStreaming: (v) => set({ isStreaming: v }),
  setEnded: () => set({ isEnded: true }),
  reset: () =>
    set({
      sessionId: null,
      messages: [],
      currentRound: 0,
      maxRounds: 12,
      isStreaming: false,
      isEnded: false,
    }),
}));
