import type { ChatMessage } from '../types';

interface Props {
  role: ChatMessage['role'];
  content: string;
  isStreaming?: boolean;
}

export default function ChatBubble({ role, content, isStreaming }: Props) {
  const isStudent = role === 'student';

  // 检查结果不是患者说的话，用独立的检查卡片渲染，避免和患者气泡混淆。
  if (role === 'exam') {
    return (
      <div className="flex mb-4 justify-start">
        <div className="max-w-[85%] flex items-start gap-2">
          <span className="text-lg shrink-0 select-none">📋</span>
          <div
            className="px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words
                       bg-blue-50/70 text-[var(--color-text)]
                       border border-blue-200/70 rounded-xl"
          >
            <div className="text-xs font-medium text-blue-700 mb-1">检查结果</div>
            {content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex mb-4 ${isStudent ? 'justify-end' : 'justify-start'}`}
    >
      <div className={`max-w-[80%] ${isStudent ? 'items-end' : 'items-start'}`}>
        <div className="flex items-end gap-2">
          {!isStudent && (
            <span className="text-lg shrink-0 select-none">🤒</span>
          )}
          <div
            className={`px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words
                        ${isStudent
                          ? 'bg-[var(--color-primary)] text-white rounded-2xl rounded-br-md'
                          : 'bg-gray-100 text-[var(--color-text)] rounded-2xl rounded-bl-md'
                        }`}
          >
            {content}
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-current ml-0.5 animate-blink align-middle" />
            )}
          </div>
          {isStudent && (
            <span className="text-lg shrink-0 select-none">🩺</span>
          )}
        </div>
      </div>
    </div>
  );
}
