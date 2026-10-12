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
  appendSystem: (content: string) => void;
  setStreaming: (v: boolean) => void;
  setEnded: () => void;
  reset: () => void;
}

export const useInterviewStore = create<InterviewState>((set, get) => ({
  sessionId: null,
  messages: [],
  currentRound: 0,
  // 0 = 未知。真实值只能来自会话接口的 max_rounds，**不要在这里写死轮数**——
  // 写死过一次 12，导致界面一直显示「第 15/12 轮」（见 CLAUDE.md 的注意点）。
  maxRounds: 0,
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

  // 系统说明（模拟资料不足）：整段文本、不流式、不计入轮次
  appendSystem: (content) =>
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: -1,
          session_id: s.sessionId || 0,
          role: 'system',
          content,
          round_num: s.currentRound,
          created_at: new Date().toISOString(),
        },
      ],
    })),

  setStreaming: (v) => set({ isStreaming: v }),
  setEnded: () => set({ isEnded: true }),
  // 清掉一次会话的**瞬时**状态。maxRounds 是会话元数据，不在这里重置——
  // 它由 setSession 从后端带进来，重置它只会把真实轮数抹掉。
  reset: () =>
    set({
      sessionId: null,
      messages: [],
      currentRound: 0,
      isStreaming: false,
      isEnded: false,
    }),
}));
