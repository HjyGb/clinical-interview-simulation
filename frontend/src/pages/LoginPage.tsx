import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { Stethoscope } from 'lucide-react';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('123456');
  const { login, loading, error } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return;
    const ok = await login(username.trim(), password);
    if (ok) navigate('/cases');
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-[#667eea] to-[#764ba2] p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-10 w-full max-w-[380px]">
        {/* Header */}
        <div className="text-center mb-8">
          <Stethoscope className="w-10 h-10 text-[var(--color-primary)] mx-auto mb-2" />
          <h1 className="text-xl font-bold text-[var(--color-text)] m-0">
            临床问诊模拟系统
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">
            AI-Powered Virtual Standardized Patient
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-[var(--color-text)] block mb-1.5">
              工号
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入工号（如 test001）"
              autoFocus
              className="w-full px-4 py-2.5 border border-[var(--color-border)] rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent
                         transition-shadow"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-[var(--color-text)] block mb-1.5">
              密码
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="输入密码"
              className="w-full px-4 py-2.5 border border-[var(--color-border)] rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent
                         transition-shadow"
            />
          </div>

          {error && (
            <p className="text-sm text-[var(--color-error)]">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim()}
            className="w-full py-3 rounded-lg font-medium text-sm transition-all
                       bg-[var(--color-primary)] text-white hover:opacity-90 active:scale-[0.98]
                       disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </form>

        <p className="text-center text-xs text-[var(--color-text-secondary)] mt-5">
          首次登录自动注册 · 测试账号 test001 / 123456
        </p>
      </div>
    </div>
  );
}
