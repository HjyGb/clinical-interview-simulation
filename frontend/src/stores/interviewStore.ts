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

  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
      currentRound: msg.role === 'patient' ? s.currentRound + 1 : s.currentRound,
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
        round_num: get().currentRound + 1,
        created_at: new Date().toISOString(),
      };
      set({ messages: [...msgs, streamMsg] });
    }
  },

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
