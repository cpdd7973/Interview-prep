import { useEffect, useRef } from 'react';

const ChatInterface = ({ messages }) => {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (!messages || messages.length === 0) {
    return (
      <div style={{ color: '#718096', textAlign: 'center', padding: '40px 16px', fontSize: '14px' }}>
        <p style={{ margin: 0 }}>Waiting for interview to begin...</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {messages.filter(msg => msg && typeof msg === 'object').map((msg, idx) => {
        const isAI = msg.speaker && msg.speaker.toLowerCase() === 'ai';
        return (
          <div key={idx} style={{
            padding: '10px 14px',
            borderRadius: '10px',
            backgroundColor: isAI ? '#2d3748' : '#2b6cb0',
            color: '#e2e8f0',
            maxWidth: '95%',
            alignSelf: isAI ? 'flex-start' : 'flex-end',
            fontSize: '14px',
            lineHeight: '1.5',
            wordBreak: 'break-word'
          }}>
            <div style={{
              fontSize: '11px',
              fontWeight: '700',
              color: isAI ? '#63b3ed' : '#bee3f8',
              marginBottom: '4px',
              textTransform: 'uppercase',
              letterSpacing: '0.05em'
            }}>
              {isAI ? '🤖 AI Interviewer' : '🎤 You'}
            </div>
            <div>{msg.text}</div>
          </div>
        );
      })}
      <div ref={endRef} />
    </div>
  );
};

export default ChatInterface;
