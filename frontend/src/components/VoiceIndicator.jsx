/**
 * VoiceIndicator.jsx - Shows when AI is speaking or listening
 */
const VoiceIndicator = ({ isAISpeaking }) => {
  return (
    <div className="voice-indicator">
      <div className={`indicator-dot ${isAISpeaking ? 'speaking' : 'listening'}`}>
        {isAISpeaking ? '🔊' : '🎤'}
      </div>
      <span className="indicator-text">
        {isAISpeaking ? 'AI is speaking...' : 'Listening...'}
      </span>
    </div>
  );
};

export default VoiceIndicator;
