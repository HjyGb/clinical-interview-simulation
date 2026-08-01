import { create } from 'zustand';
import type { UserInfo } from '../types';
import { login as apiLogin, getMe } from '../api/auth';

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('token'),
  user: null,
  loading: false,
  error: null,

  login: async (username, password) => {
    set({ loading: true, error: null });
    try {
      const result = await apiLogin({ username, password });
      localStorage.setItem('token', result.access_token);
      set({
        token: result.access_token,
        user: { id: 0, username: result.username, role: result.role },
        loading: false,
      });
      return true;
    } catch (e) {
      set({ loading: false, error: (e as Error).message });
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ token: null, user: null });
  },

  checkAuth: async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
      const user = await getMe();
      set({ token, user });
    } catch {
      localStorage.removeItem('token');
      set({ token: null, user: null });
    }
  },
}));
