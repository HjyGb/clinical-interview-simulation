import { apiGet, apiPost } from './client';
import type { AssessmentResult, DiagnosisSubmit } from '../types';

export function submitAssessment(sessionId: number, diagnosis: DiagnosisSubmit): Promise<AssessmentResult> {
  return apiPost<AssessmentResult>(`/sessions/${sessionId}/assessment`, diagnosis);
}

export function getAssessment(sessionId: number): Promise<AssessmentResult> {
  return apiGet<AssessmentResult>(`/sessions/${sessionId}/assessment`);
}
