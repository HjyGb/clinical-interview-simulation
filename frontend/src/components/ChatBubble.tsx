interface Props {
  role: 'student' | 'patient';
  content: string;
  isStreaming?: boolean;
}

export default function ChatBubble({ role, content, isStreaming }: Props) {
  const isStudent = role === 'student';

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
