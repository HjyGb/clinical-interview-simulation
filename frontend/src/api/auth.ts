import { apiGet, apiPost } from './client';
import type { LoginRequest, LoginResponse, UserInfo } from '../types';

export function login(req: LoginRequest): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/auth/login', req);
}

export function getMe(): Promise<UserInfo> {
  return apiGet<UserInfo>('/auth/me');
}
