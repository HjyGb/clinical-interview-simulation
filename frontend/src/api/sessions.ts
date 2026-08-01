import { apiGet, apiPost, apiPostSSE } from './client';
import type { SessionInfo, ChatMessage } from '../types';

export function createSession(caseId: number): Promise<SessionInfo> {
  return apiPost<SessionInfo>('/sessions', { case_id: caseId });
}

export function getSession(id: number): Promise<SessionInfo> {
  return apiGet<SessionInfo>(`/sessions/${id}`);
}

export function getMessages(sessionId: number): Promise<{ messages: ChatMessage[]; total: number }> {
  return apiGet(`/sessions/${sessionId}/messages`);
}

export function sendMessage(
  sessionId: number,
  content: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  return apiPostSSE(`/sessions/${sessionId}/messages`, { content }, onEvent, signal);
}

export function endSession(sessionId: number): Promise<{ status: string }> {
  return apiPost(`/sessions/${sessionId}/end`);
}
