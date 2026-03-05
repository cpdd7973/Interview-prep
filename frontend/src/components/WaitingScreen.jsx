/**
 * WaitingScreen.jsx - Holding screen during early entry window
 */
const WaitingScreen = ({ candidateName, secondsRemaining }) => {
  const minutesLeft = Math.ceil(secondsRemaining / 60);

  return (
    <div className="waiting-screen">
      <div className="waiting-content">
        <div className="waiting-icon">
          <div className="pulse-ring"></div>
          <div className="waiting-avatar">👤</div>
        </div>
        <h2>Welcome, {candidateName}!</h2>
        <p className="waiting-message">
          Your interviewer will join shortly.
        </p>
        <p className="waiting-time">
          Interview starts in approximately {minutesLeft} {minutesLeft === 1 ? 'minute' : 'minutes'}
        </p>
        <div className="waiting-tips">
          <h3>While you wait:</h3>
          <ul>
            <li>✓ Ensure your microphone is working</li>
            <li>✓ Find a quiet environment</li>
            <li>✓ Have a glass of water nearby</li>
            <li>✓ Take a deep breath and relax</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

export default WaitingScreen;
