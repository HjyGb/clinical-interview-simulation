import { apiGet } from './client';
import type { CaseSummary, CaseDetail } from '../types';

export function listCases(): Promise<{ cases: CaseSummary[]; total: number }> {
  return apiGet('/cases?page_size=200');
}

export function getCase(id: number): Promise<CaseDetail> {
  return apiGet(`/cases/${id}`);
}
