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
  case_number: string;
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
  // exam = 检查结果。不是患者说的话，单独渲染成检查卡片。
  role: 'student' | 'patient' | 'exam';
  content: string;
  round_num: number;
  created_at: string;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/** 学员答卷五项，一一对应 R06–R10。字段名以后端 scoring.llm_judge.ANSWER_FIELDS 为准。 */
export interface DiagnosisSubmit {
  /** ① 诊断（部位 + 确定性） */
  primary_diagnosis: string;
  /** ② 诊断理由（推理链，不是只报病名） */
  diagnosis_reason: string;
  /** ③ 鉴别诊断（含区分依据） */
  differential_diagnosis: string;
  /** ④ 近期处理 */
  immediate_plan: string;
  /** ⑤ 阶段计划与复评 */
  staged_plan: string;
}

export type ItemStatus = 'scored' | 'ne' | 'na' | 'skipped_safety';

export interface ScoringEvidence {
  n: number;
  met: boolean;
  quote: string;
  ref: string;
  downgraded: boolean;
}

export interface ScoringItem {
  id: string;
  name: string;
  score: number;
  max_score: number;
  status: ItemStatus;
  note: string;
  evidence: ScoringEvidence[];
}

export interface ViewGroup {
  name: string;
  items: string[];
  score: number;
  max: number;
}

export interface ScoringView {
  name: string;
  groups: ViewGroup[];
}

export interface SafetyFlag {
  index: number;
  error: string;
  hit: boolean;
  evidence_quote: string;
  evidence_ref: string;
  checked: boolean;
}

export interface SafetyReport {
  flags: SafetyFlag[];
  hits: number;
  unchecked: number;
  requires_review: boolean;
  safety_priority_case: boolean;
  stop_evidence: string;
}

export interface ScoringTotal {
  raw_total: number;
  /** 可评上限：NE/NA 扣掉后真正可能拿到的上限 */
  raw_max_counted: number;
  /** 名义满分（14 × 2 = 28） */
  raw_max_nominal: number;
  excluded: Record<string, string[]>;
}

export interface AssessmentReport {
  items: ScoringItem[];
  views: ScoringView[];
  total: ScoringTotal;
  safety: SafetyReport;
  system_errors: number;
  scoring_note: string;
}

export interface AssessmentResult {
  id: number;
  session_id: number;
  report: AssessmentReport;
  raw_total: number;
  comment: string | null;
  student_report?: DiagnosisSubmit;
  created_at: string;
}

export interface SessionListItem {
  id: number;
  case_id: number;
  case_title: string;
  case_department: string;
  case_difficulty: string;
  status: string;
  max_rounds: number;
  has_assessment: boolean;
  assessment_id: number | null;
  started_at: string;
  ended_at: string | null;
}
