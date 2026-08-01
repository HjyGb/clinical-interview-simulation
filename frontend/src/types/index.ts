/* TypeScript types matching backend Pydantic schemas */

export interface UserInfo {
  id: number;
  username: string;
  role: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
  role: string;
}

export interface CaseSummary {
  id: number;
  title: string;
  department: string;
  difficulty: string;
  visit_type: string;
  chief_complaint: string;
}

export interface CaseDetail {
  id: number;
  title: string;
  department: string;
  difficulty: string;
  data: Record<string, unknown>;
}

export interface SessionInfo {
  id: number;
  user_id: number;
  case_id: number;
  status: string;
  max_rounds: number;
  current_round: number;
  started_at: string;
  ended_at: string | null;
}

export interface ChatMessage {
  id: number;
  session_id: number;
  role: 'student' | 'patient';
  content: string;
  round_num: number;
  created_at: string;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface DiagnosisSubmit {
  primary_diagnosis: string;
  differential_diagnosis: string;
  evidence: string;
  suggested_exams: string;
  treatment_plan: string;
}

export interface ScoreDimension {
  name: string;
  score: number;
  max_score: number;
  justification: string;
  missed_items: string[];
  suggestions: string[];
}

export interface AssessmentBlock {
  total_score: number;
  max_score: number;
  dimensions: ScoreDimension[];
}

export interface AssessmentResult {
  id: number;
  session_id: number;
  diagnostic: AssessmentBlock;
  communication: AssessmentBlock;
  comment: string | null;
  created_at: string;
}
