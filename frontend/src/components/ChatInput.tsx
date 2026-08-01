import { useState } from 'react';
import { Send } from 'lucide-react';

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
    <div className="flex gap-2.5 px-4 py-3 border-t border-[var(--color-border)] bg-white">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder || '输入你的问诊问题...'}
        className="flex-1 px-4 py-2.5 border border-[var(--color-border)] rounded-lg text-sm
                   focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:border-transparent
                   disabled:bg-gray-50 disabled:text-gray-400 transition-shadow"
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        className="flex items-center gap-1.5 px-5 py-2.5 rounded-lg font-medium text-sm
                   transition-all active:scale-[0.98]
                   bg-[var(--color-primary)] text-white hover:opacity-90
                   disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed"
      >
        <Send className="w-4 h-4" />
        <span>发送</span>
      </button>
    </div>
  );
}
