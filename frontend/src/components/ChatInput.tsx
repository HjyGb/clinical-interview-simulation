import { useState } from 'react';

interface Props {
  onSend: (content: string) => void;
  disabled: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, disabled, placeholder }: Props) {
  const [text, setText] = useState('');

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{
      display: 'flex',
      gap: 10,
      padding: '12px 16px',
      borderTop: '1px solid #e8e8e8',
      background: '#fff',
    }}>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder || '输入你的问诊问题...'}
        style={{
          flex: 1,
          padding: '10px 16px',
          border: '1px solid #d9d9d9',
          borderRadius: 8,
          fontSize: 15,
          outline: 'none',
        }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        style={{
          padding: '10px 24px',
          background: disabled || !text.trim() ? '#d9d9d9' : '#1677ff',
          color: '#fff',
          border: 'none',
          borderRadius: 8,
          fontSize: 15,
          cursor: disabled || !text.trim() ? 'not-allowed' : 'pointer',
        }}
      >
        发送
      </button>
    </div>
  );
}
