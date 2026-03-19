import React, { useState, useEffect, useRef } from 'react';

const PreJoinScreen = ({ roomState, onJoin }) => {
  const [micStatus, setMicStatus] = useState('untested'); // 'untested', 'testing', 'success', 'error'
  const [isInsecure, setIsInsecure] = useState(false);
  
  useEffect(() => {
    // Detect if we are in an insecure context (HTTP on non-localhost)
    if (!window.isSecureContext && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      setIsInsecure(true);
      // Don't set status to error immediately, let them try 'Test Mic' after setting flags
    }
  }, []);

  const [audioStream, setAudioStream] = useState(null);
  const [volume, setVolume] = useState(0);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const animationFrameRef = useRef(null);

  useEffect(() => {
    return () => {
      // Cleanup audio context and stream on unmount
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close().catch(console.error);
      }
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [audioStream]);

  const testMicrophone = async () => {
    setMicStatus('testing');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setAudioStream(stream);

      // Create audio context to visualize volume
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioContext();
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      const updateVolume = () => {
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const average = sum / dataArray.length;
        setVolume(Math.min(100, (average / 128) * 100)); // Normalize volume

        animationFrameRef.current = requestAnimationFrame(updateVolume);
      };

      updateVolume();
      setMicStatus('success');

    } catch (err) {
      console.error("Microphone test failed:", err);
      setMicStatus('error');
    }
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', backgroundColor: '#f0f4f8', fontFamily: "'Inter', sans-serif"
    }}>
      <div style={{
        backgroundColor: 'white', padding: '40px', borderRadius: '16px',
        boxShadow: '0 10px 30px rgba(0,0,0,0.05)', maxWidth: '500px', width: '100%'
      }}>

        <div style={{ textAlign: 'center', marginBottom: '30px' }}>
          <h1 style={{ margin: '0 0 10px 0', fontSize: '24px', color: '#1a202c' }}>Ready to Join?</h1>
          <p style={{ margin: 0, color: '#4a5568', fontSize: '15px' }}>
            {roomState.company} - {roomState.job_role}
          </p>
        </div>

        <div style={{ backgroundColor: '#f7fafc', padding: '20px', borderRadius: '12px', marginBottom: '30px' }}>
          <h3 style={{ margin: '0 0 15px 0', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#718096' }}>Candidate Details</h3>
          <p style={{ margin: '0 0 8px 0', fontWeight: '500' }}>Name: <span style={{ fontWeight: 'normal' }}>{roomState.candidate_name}</span></p>
          <p style={{ margin: '0 0 8px 0', fontWeight: '500' }}>Interviewer: <span style={{ fontWeight: 'normal' }}>{roomState.interviewer_designation} (AI)</span></p>
        </div>

        <div style={{ marginBottom: '30px' }}>
          <h3 style={{ margin: '0 0 15px 0', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#718096' }}>Equipment Check</h3>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '15px', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '20px' }}>🎙️</span>
              <span style={{ fontWeight: '500', color: '#2d3748' }}>Microphone</span>
            </div>

            {micStatus === 'untested' && (
              <button
                onClick={testMicrophone}
                style={{ padding: '6px 12px', background: '#edf2f7', color: '#4a5568', border: '1px solid #cbd5e0', borderRadius: '6px', cursor: 'pointer', fontSize: '12px', fontWeight: '600' }}
              >
                Test Mic
              </button>
            )}
            {micStatus === 'testing' && <span style={{ color: '#718096', fontSize: '13px' }}>Testing...</span>}
            {micStatus === 'error' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#e53e3e', fontSize: '13px', fontWeight: '500' }}>Access Denied</span>
                <button
                  onClick={testMicrophone}
                  style={{ padding: '4px 8px', background: 'white', color: '#c53030', border: '1px solid #feb2b2', borderRadius: '4px', cursor: 'pointer', fontSize: '11px', fontWeight: '600' }}
                >
                  Retry
                </button>
              </div>
            )}
            {micStatus === 'success' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '60px', height: '6px', backgroundColor: '#edf2f7', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${Math.max(5, volume)}%`, backgroundColor: volume > 10 ? '#48bb78' : '#cbd5e0', transition: 'width 0.1s ease-out' }}></div>
                </div>
                <span style={{ color: '#48bb78', fontSize: '14px' }}>✓</span>
              </div>
            )}
          </div>
          {micStatus === 'error' && (
            <div style={{ marginTop: '15px', padding: '12px', backgroundColor: '#fff5f5', border: '1px solid #feb2b2', borderRadius: '8px' }}>
              <p style={{ color: '#c53030', fontSize: '13px', margin: '0 0 8px 0', fontWeight: '600' }}>
                {isInsecure ? '🚨 Insecure Connection Detected' : '❌ Microphone Access Denied'}
              </p>
              <p style={{ color: '#742a2a', fontSize: '12px', margin: 0, lineHeight: '1.5' }}>
                {isInsecure ? (
                  <>
                    Browsers block microphone access on <b>http://</b> sites. To fix this:
                    <ol style={{ margin: '8px 0 0 20px', padding: 0 }}>
                      <li>Open <b>chrome://flags/#unsafely-treat-insecure-origin-as-secure</b></li>
                      <li>In the text box, paste exactly: <code style={{ backgroundColor: '#fff', padding: '2px 4px', border: '1px solid #ddd' }}>{window.location.origin}</code></li>
                      <li>Select <b>Enabled</b> in the dropdown</li>
                      <li>Click the <b>Relaunch</b> button at the bottom</li>
                    </ol>
                  </>
                ) : (
                  'Please allow microphone permissions in your browser settings to continue.'
                )}
              </p>
            </div>
          )}
        </div>

        <button
          onClick={async () => {
            // Ensure AudioContext is ready for Safari/Mobile before joining
            const ctx = window.AudioContext || window.webkitAudioContext;
            if (ctx) {
              const tempCtx = new ctx();
              await tempCtx.resume();
            }
            onJoin();
          }}
          disabled={micStatus === 'error' && !isInsecure}
          style={{
            width: '100%', padding: '16px', fontSize: '16px', fontWeight: '600',
            backgroundColor: (micStatus === 'error' && !isInsecure) ? '#cbd5e0' : '#3182ce',
            color: 'white', border: 'none', borderRadius: '8px',
            cursor: (micStatus === 'error' && !isInsecure) ? 'not-allowed' : 'pointer',
            transition: 'background-color 0.2s', boxShadow: '0 4px 6px rgba(49, 130, 206, 0.2)'
          }}
        >
          {micStatus === 'untested' ? 'Join Without Testing' : 'Join Interview'}
        </button>

      </div>
    </div>
  );
};

export default PreJoinScreen;
