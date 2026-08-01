interface Props {
  role: 'student' | 'patient';
  content: string;
  isStreaming?: boolean;
}

export default function ChatBubble({ role, content, isStreaming }: Props) {
  const isStudent = role === 'student';
  return (
    <div style={{
      display: 'flex',
      justifyContent: isStudent ? 'flex-end' : 'flex-start',
      marginBottom: 16,
    }}>
      <div style={{
        maxWidth: '70%',
        padding: '12px 18px',
        borderRadius: 16,
        borderTopRightRadius: isStudent ? 4 : 16,
        borderTopLeftRadius: isStudent ? 16 : 4,
        background: isStudent ? '#1677ff' : '#f0f0f0',
        color: isStudent ? '#fff' : '#333',
        fontSize: 15,
        lineHeight: 1.6,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {role === 'patient' && (
          <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>🤒 患者</div>
        )}
        {content}
        {isStreaming && <span style={{
          display: 'inline-block',
          width: 8,
          height: 16,
          background: '#999',
          marginLeft: 2,
          animation: 'blink 0.8s infinite',
        }} />}
      </div>
    </div>
  );
}
