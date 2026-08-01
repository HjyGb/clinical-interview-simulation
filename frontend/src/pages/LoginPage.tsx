import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

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
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 16,
        padding: '40px 36px',
        width: 380,
        boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <h1 style={{ fontSize: 28, margin: 0 }}>🩺</h1>
          <h2 style={{ margin: '8px 0 4px', fontSize: 20 }}>临床问诊模拟系统</h2>
          <p style={{ margin: 0, color: '#999', fontSize: 14 }}>AI-Powered Virtual Standardized Patient</p>
        </div>

        <form onSubmit={handleSubmit}>
          <label style={{ fontSize: 14, fontWeight: 500, marginBottom: 4, display: 'block' }}>工号</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入工号（如 test001）"
            autoFocus
            style={{
              width: '100%',
              padding: '12px 16px',
              border: '1px solid #d9d9d9',
              borderRadius: 8,
              fontSize: 16,
              marginBottom: 16,
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />

          <label style={{ fontSize: 14, fontWeight: 500, marginBottom: 4, display: 'block' }}>密码</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="输入密码"
            style={{
              width: '100%',
              padding: '12px 16px',
              border: '1px solid #d9d9d9',
              borderRadius: 8,
              fontSize: 16,
              marginBottom: 24,
              boxSizing: 'border-box',
              outline: 'none',
            }}
          />

          {error && (
            <p style={{ color: '#ff4d4f', fontSize: 14, marginBottom: 16 }}>{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim()}
            style={{
              width: '100%',
              padding: '12px',
              background: loading ? '#d9d9d9' : '#1677ff',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 16,
              fontWeight: 500,
              cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </form>

        <p style={{ textAlign: 'center', color: '#bbb', fontSize: 12, marginTop: 20 }}>
          首次登录自动注册 · 测试账号 test001 / 123456
        </p>
      </div>
    </div>
  );
}
