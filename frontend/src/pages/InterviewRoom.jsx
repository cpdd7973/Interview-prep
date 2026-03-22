/**
 * InterviewRoom.jsx - Candidate-facing interview room with time gate
 * 
 * States:
 * - PENDING: Shows countdown timer until scheduled time
 * - EARLY_ENTRY: 5 minutes before, shows waiting screen
 * - ACTIVE: Interview is live, loads Daily.co iframe
 * - COMPLETED: Interview finished
 * - EXPIRED: Session timed out
 * - CANCELLED: Interview was cancelled
 */
import { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import CountdownTimer from '../components/CountdownTimer';
import WaitingScreen from '../components/WaitingScreen';
import VoiceIndicator from '../components/VoiceIndicator';
import ChatInterface from '../components/ChatInterface';
import { getRoomStatus } from '../services/api';
import PreJoinScreen from '../components/PreJoinScreen';

const ActiveTimer = () => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsed(prev => prev + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const mins = Math.floor(elapsed / 60);
  const secs = Math.floor(elapsed % 60);
  return <span className="active-timer" style={{ marginLeft: '15px', fontWeight: 'bold' }}>{String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}</span>;
};

const POLL_INTERVAL = 30000; // 30 seconds
const EARLY_ENTRY_SECONDS = 5 * 60; // 5 minutes

const InterviewRoom = () => {
  const { roomId } = useParams();
  const [roomState, setRoomState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isAISpeaking, setIsAISpeaking] = useState(false);
  const [pendingCompletion, setPendingCompletion] = useState(false);
  const [forceCompleted, setForceCompleted] = useState(false); // Overrides polling
  const [isAIOptedIn, setIsAIOptedIn] = useState(false);
  const [messages, setMessages] = useState([]);
  const pollTimerRef = useRef(null);
  const abortControllerRef = useRef(null);
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recognitionStoppedRef = useRef(false);
  const pendingTranscriptRef = useRef(null);
  const audioFallbackTimeoutRef = useRef(null);
  const recognitionRef = useRef(null);

  // Emergency browser STT fallback
  const [manualText, setManualText] = useState("");

  // ── New Diagnostic & Fallback States ──
  const [micActive, setMicActive] = useState(false);
  const [bytesSent, setBytesSent] = useState(0);
  const [lastAudioReceivedAt, setLastAudioReceivedAt] = useState(null);
  const ttsFallbackTimerRef = useRef(null);
  const lastAITextRef = useRef(null);

  // Fetch room status
  const fetchRoomStatus = async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();

    try {
      const data = await getRoomStatus(roomId, abortControllerRef.current.signal);

      if (data.success) {
        setRoomState(data);
        setError(null);
      } else {
        setError(data.error || 'Failed to fetch room status');
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Error fetching room status:', err);
        setError('Unable to connect to server');
      }
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchRoomStatus();

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [roomId]);

  // Polling logic based on status
  useEffect(() => {
    if (!roomState) return;

    const { status, seconds_remaining } = roomState;

    // Clear existing timer
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    // Only poll if status is PENDING, ACTIVE, or DISCONNECTED
    if (status === 'PENDING' || status === 'ACTIVE' || status === 'DISCONNECTED') {
      // For PENDING with less than 10 minutes remaining, or if DISCONNECTED, poll more frequently
      const pollInterval = (status === 'PENDING' && seconds_remaining < 600) || status === 'DISCONNECTED'
        ? 10000  // 10 seconds
        : POLL_INTERVAL;

      pollTimerRef.current = setInterval(fetchRoomStatus, pollInterval);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [roomState?.status, roomState?.seconds_remaining]);

  // Determine current view state
  const getViewState = () => {
    if (!roomState) return 'LOADING';

    const { status, seconds_remaining, finished_at } = roomState;

    if (forceCompleted) return 'COMPLETED';

    if (status === 'ACTIVE' || status === 'DISCONNECTED') {
      if (finished_at) return 'COMPLETED';
      return 'ACTIVE'; // Treat DISCONNECTED as ACTIVE for the room UI to allow reconnections
    }
    if (status === 'COMPLETED') return 'COMPLETED';
    if (status === 'EXPIRED') return 'EXPIRED';
    if (status === 'CANCELLED') return 'CANCELLED';

    // If more than 60 minutes past scheduled time, treat as expired locally to prevent late joins
    if (seconds_remaining < -3600) {
      return 'EXPIRED';
    }

    // PENDING state - check if early entry allowed
    if (status === 'PENDING') {
      if (seconds_remaining <= 0) {
        return 'READY';
      }
      if (seconds_remaining <= EARLY_ENTRY_SECONDS) {
        return 'EARLY_ENTRY';
      }
      return 'COUNTDOWN';
    }

    return 'LOADING';
  };

  const viewState = getViewState();

  // ──────────────────────────────────────────────────────────────────
  // Priya's Real Fix: Drop Chrome SpeechRecognition entirely.
  // Use MediaRecorder to capture mic audio as WebM blobs.
  // Send raw audio to backend → Groq Whisper transcribes server-side.
  //
  // KEY FIX: Stop/restart MediaRecorder every 6s to produce COMPLETE
  // WebM files (with headers). Concatenating continuation chunks
  // produces invalid files that Groq rejects with 400.
  // ──────────────────────────────────────────────────────────────────

  const isAISpeakingRef = useRef(false);
  const micStreamRef = useRef(null);
  const recordingCycleRef = useRef(null);

  // VAD Refs
  const isSpeakingRef = useRef(false);
  const speechStartRef = useRef(null); // When sound first crossed threshold
  const silenceStartRef = useRef(null);

  // Keep ref in sync with state
  useEffect(() => {
    isAISpeakingRef.current = isAISpeaking;
  }, [isAISpeaking]);

  // Start a single recording cycle: record continuously until VAD detects silence
  const startRecordingCycle = (ws, stream) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    
    const chunks = [];
    
    // Hardened MIME type selection
    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
      'audio/wav'
    ];
    
    let mimeType = '';
    for (const type of mimeTypes) {
      if (MediaRecorder.isTypeSupported(type)) {
        mimeType = type;
        break;
      }
    }
    
    if (!mimeType) {
      console.error("No supported MediaRecorder MIME types found");
      return;
    }

    try {
      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;
      setMicActive(true);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
          // REMOVED redundant ws.send(e.data) to prevent double-send and invalid fragments
        }
      };

      recorder.onstop = () => {
        setMicActive(false);
        // ECHO GUARD: If AI is speaking, this recording contains echo — discard it
        if (isAISpeakingRef.current) {
          console.log("[MIC] 🗑️ Discarding recording (AI was speaking — it's echo)");
          return;
        }

        // Send the accumulated WebM blob
        if (chunks.length > 0) {
          const blob = new Blob(chunks, { type: 'audio/webm' });
          if (blob.size > 1000 && ws.readyState === WebSocket.OPEN) {
            console.log(`[MIC] 📤 Sending complete ${blob.size} byte recording (VAD triggered)`);
            ws.send(blob);
            setBytesSent(prev => prev + blob.size);
          }
        }

        // Start the next cycle immediately to catch the next utterance
        if (ws.readyState === WebSocket.OPEN && !isAISpeakingRef.current) {
          recordingCycleRef.current = setTimeout(() => {
            startRecordingCycle(ws, stream);
          }, 50);
        }
      };

      recorder.start();
      console.log(`[MIC] 🎙️ Recording cycle started with ${mimeType}`);
    } catch (err) {
      console.error("Error in recording cycle:", err);
      setMicActive(false);
    }
  };

  // Initialize mic — gets stream once, but does NOT start recording.
  // Recording only starts when isAISpeaking transitions from true → false
  // (i.e., after the AI greeting finishes playing).
  const [micLevel, setMicLevel] = useState(0);
  const analyserRef = useRef(null);
  const micLevelIntervalRef = useRef(null);

  const initMicStream = async () => {
    try {
      // STEP 1: Get generic permission first — device labels are EMPTY until
      // the user grants mic access. We need labels to identify virtual cables.
      const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      tempStream.getTracks().forEach(t => t.stop()); // Release immediately
      console.log("[MIC] ✅ Permission granted. Now enumerating devices with labels...");

      // STEP 2: NOW enumerate — labels will be populated after permission
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devices.filter(d => d.kind === 'audioinput');
      console.log(`[MIC] Found ${audioInputs.length} audio input devices:`);
      audioInputs.forEach((d, i) => {
        const isVirtual = /virtual|vb-audio|cable|loopback|stereo mix/i.test(d.label);
        console.log(`[MIC]   ${i}: "${d.label}" ${isVirtual ? '⚠️ VIRTUAL' : '✅ PHYSICAL'}`);
      });

      // STEP 3: Find a REAL microphone — skip virtual cables
      const physicalMic = audioInputs.find(d => {
        const label = d.label.toLowerCase();
        return label && !/virtual|vb-audio|cable|loopback|stereo mix|wave out/.test(label);
      });

      // Build audio constraints with specific device
      const audioConstraints = {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
        channelCount: 1,
      };

      if (physicalMic && physicalMic.deviceId) {
        audioConstraints.deviceId = { exact: physicalMic.deviceId };
        console.log(`[MIC] ✅ Selected PHYSICAL mic: "${physicalMic.label}"`);
      } else {
        console.warn("[MIC] ⚠️ Could not identify physical mic. Trying default device.");
      }

      // STEP 4: Get the REAL mic stream
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      micStreamRef.current = stream;

      // Log all available audio tracks for debugging
      const tracks = stream.getAudioTracks();
      console.log(`[MIC] 🎙️ Microphone access granted. Tracks: ${tracks.length}`);
      tracks.forEach(t => console.log(`[MIC]   Track: ${t.label} (${t.readyState}, enabled=${t.enabled})`));

      // Set up audio level monitoring to verify mic is working
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      // CRITICAL: Chrome suspends AudioContext until resume() is called
      await audioCtx.resume();
      console.log(`[MIC] AudioContext state: ${audioCtx.state}`);

      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      // Use TimeDomain data (raw waveform) — much more reliable for detecting speech
      // Values center at 128 (silence). Deviation from 128 = audio activity.
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      micLevelIntervalRef.current = setInterval(() => {
        analyser.getByteTimeDomainData(dataArray);
        // Calculate RMS (root mean square) deviation from silence (128)
        let sumSquares = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const deviation = dataArray[i] - 128;
          sumSquares += deviation * deviation;
        }
        const rms = Math.sqrt(sumSquares / dataArray.length);
        const level = Math.round(rms);
        setMicLevel(level);

        // VAD LOGIC
        // Only monitor for candidate speech if AI is NOT speaking and recorder is active
        if (!isAISpeakingRef.current && mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
          // Expert VAD (Priya): Threshold 3, Min Duration 400ms
          const VAD_THRESHOLD = 3;
          const MIN_SPEECH_MS = 400;
          const SILENCE_TIMEOUT = 1500; // Snappier send (1.5s vs 2s)

          if (level > VAD_THRESHOLD) {
            if (!isSpeakingRef.current) {
              // Start tracking potential speech
              if (!speechStartRef.current) {
                speechStartRef.current = Date.now();
                console.log("[VAD] 👂 Hearing something...");
              } else if (Date.now() - speechStartRef.current > MIN_SPEECH_MS) {
                console.log("[VAD] 🗣️ Speech confirmed (min duration hit)");
                isSpeakingRef.current = true;
              }
            }
            // Reset silence timer because they are speaking
            silenceStartRef.current = null;
          } else {
            // Silence detected
            speechStartRef.current = null; // Reset "hearing" state if it was just a click

            if (isSpeakingRef.current) {
              if (!silenceStartRef.current) {
                silenceStartRef.current = Date.now();
              } else if (Date.now() - silenceStartRef.current > SILENCE_TIMEOUT) {
                console.log("[VAD] 🤫 Turn ended (silence detected).");
                isSpeakingRef.current = false;
                silenceStartRef.current = null;
                mediaRecorderRef.current.stop();
              }
            }
          }
        }
      }, 100);
    } catch (err) {
      console.error("[MIC] ❌ Microphone access denied:", err);
      alert("Microphone access is required for voice interview. Please allow microphone access and refresh.");
    }
  };

  // Setup WebSocket when ACTIVE and User has opted in
  useEffect(() => {
    if ((viewState !== 'ACTIVE' && viewState !== 'READY') || !isAIOptedIn) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    
    // Robust WebSocket URL construction
    let wsUrl;
    if (import.meta.env.VITE_API_BASE_URL) {
      // Remove any trailing slash and /api if present to avoid duplication
      const base = import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '').replace(/\/api$/, '');
      wsUrl = base.replace('http', 'ws') + `/api/interviews/${roomId}/ws`;
    } else {
      wsUrl = `${wsProtocol}//${window.location.host}/api/interviews/${roomId}/ws`;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    // ── Dmitri's Pattern: WebSocket heartbeat every 15s ──
    let heartbeatInterval = null;

    ws.onopen = () => {
      console.log("WebSocket connected for audio streaming");

      // Signal backend that frontend is ready
      ws.send(JSON.stringify({ type: 'start' }));

      // Dmitri: heartbeat keeps connection alive
      heartbeatInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 15000);

      // Only acquire mic stream — do NOT start recording yet.
      // Recording starts after the AI greeting finishes playing
      // (handled by the isAISpeaking effect below).
      initMicStream();
    };

    ws.onmessage = async (event) => {
      if (event.data instanceof Blob) {
        // AI Audio response received
        setIsAISpeaking(true);
        setLastAudioReceivedAt(Date.now());
        
        // Clear fallback timer if it exists
        if (ttsFallbackTimerRef.current) {
          clearTimeout(ttsFallbackTimerRef.current);
          ttsFallbackTimerRef.current = null;
        }

        const audioUrl = URL.createObjectURL(event.data);
        const audio = new Audio(audioUrl);

        audio.onended = () => {
          URL.revokeObjectURL(audioUrl);
          setTimeout(() => {
            setIsAISpeaking(false);
          }, 500);
        };

        try {
          await audio.play();
        } catch (e) {
          console.error("Audio playback failed:", e);
          setIsAISpeaking(false);
        }
      } else {
        const data = JSON.parse(event.data);
        console.log("WebSocket Message:", data);
        
        if (data.type === 'transcript') {
          setMessages(prev => [...prev, { speaker: data.speaker, text: data.text }]);
          
          // ── TTS Fallback Logic ──
          // If AI speaks but we haven't received audio blob within 2.5s, use browser TTS
          if (data.speaker === 'AI') {
            setIsAISpeaking(true); // Signal AI is "speaking" to block candidate mic
            lastAITextRef.current = data.text; // Store for audio_failed fallback
            
            ttsFallbackTimerRef.current = setTimeout(() => {
              console.warn("⚠️ Backend TTS failed/timed out. Using Browser Web Speech API as fallback.");
              const utterance = new SpeechSynthesisUtterance(data.text);
              utterance.lang = 'en-US';
              
              utterance.onend = () => {
                setTimeout(() => setIsAISpeaking(false), 500);
              };
              
              utterance.onerror = (err) => {
                console.error("Browser TTS Error:", err);
                setIsAISpeaking(false);
              };

              window.speechSynthesis.speak(utterance);
            }, 2500);
          }
        } else if (data.type === 'interview_complete') {
          console.log("🎉 Interview completed signal received.");
          setPendingCompletion(true);
        } else if (data.type === 'audio_failed') {
          console.warn("⚠️ AI Audio generation failed. Using browser TTS fallback.");
          // Clear the delayed fallback timer — we'll trigger TTS immediately
          if (ttsFallbackTimerRef.current) {
            clearTimeout(ttsFallbackTimerRef.current);
            ttsFallbackTimerRef.current = null;
          }
          // Immediately use browser TTS with the stored AI text
          const aiText = lastAITextRef.current;
          if (aiText && window.speechSynthesis) {
            setIsAISpeaking(true);
            const utterance = new SpeechSynthesisUtterance(aiText);
            utterance.lang = 'en-US';
            utterance.onend = () => {
              setTimeout(() => setIsAISpeaking(false), 500);
            };
            utterance.onerror = (err) => {
              console.error("Browser TTS Error:", err);
              setIsAISpeaking(false);
            };
            window.speechSynthesis.speak(utterance);
          } else {
            setIsAISpeaking(false);
          }
        } else if (data.type === 'pong') {
          // Heartbeat response
        }
      }
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      if (recordingCycleRef.current) clearTimeout(recordingCycleRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };

    return () => {
      if (heartbeatInterval) clearInterval(heartbeatInterval);
      if (recordingCycleRef.current) clearTimeout(recordingCycleRef.current);
      if (micLevelIntervalRef.current) clearInterval(micLevelIntervalRef.current);
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [roomId, viewState, isAIOptedIn]);

  // ── Pause/resume mic recording based on AI speaking state ──
  // KEY: Cooldown after AI stops to let speaker echo dissipate
  useEffect(() => {
    if (isAISpeaking) {
      // Stop current recording cycle while AI speaks
      if (recordingCycleRef.current) {
        clearTimeout(recordingCycleRef.current);
        recordingCycleRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        console.log("[MIC] ⏸️ Stopping mic while AI speaks...");
        mediaRecorderRef.current.stop();
      }
    } else {
      // AI finished — wait a brief moment for speaker echo to dissipate, then start recording
      // ECHO GUARD: Increased from 500ms to 800ms for Oracle Cloud environment
      if (wsRef.current?.readyState === WebSocket.OPEN && micStreamRef.current) {
        console.log("[MIC] ⏳ AI finished. Waiting 800ms for echo to clear...");
        recordingCycleRef.current = setTimeout(() => {
          console.log("[MIC] ▶️ Starting mic capture now");
          startRecordingCycle(wsRef.current, micStreamRef.current);
        }, 800);
      }
    }
  }, [isAISpeaking]);

  // Transition to completed UI when AI finishes speaking the final message
  useEffect(() => {
    if (pendingCompletion && !isAISpeaking) {
      console.log("🎉 AI finished speaking. Forcing UI transition to COMPLETED.");
      setForceCompleted(true);
      setRoomState(prev => ({ ...prev, status: 'COMPLETED' }));
    }
  }, [pendingCompletion, isAISpeaking]);

  // ── Priya's text fallback: Send typed text directly via WebSocket ──
  const handleManualSend = () => {
    if (manualText.trim().length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'browser_stt', text: manualText.trim() }));
      setManualText("");
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="interview-room loading">
        <div className="spinner"></div>
        <p>Loading interview room...</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="interview-room error">
        <div className="error-message">
          <span className="error-icon">⚠️</span>
          <h2>Error</h2>
          <p>{error}</p>
          <button onClick={() => { setError(null); setLoading(true); fetchRoomStatus(); }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!roomState) return null;

  // Countdown state
  if (viewState === 'COUNTDOWN') {
    return (
      <div className="interview-room countdown">
        <div className="countdown-container">
          <h1>Interview Scheduled</h1>
          <div className="interview-details">
            <p><strong>Candidate:</strong> {roomState.candidate_name}</p>
            <p><strong>Role:</strong> {roomState.job_role}</p>
            <p><strong>Company:</strong> {roomState.company}</p>
          </div>
          <CountdownTimer
            secondsRemaining={roomState.seconds_remaining}
            scheduledAt={roomState.scheduled_at}
          />
          <p className="countdown-message">
            You can join {Math.floor(EARLY_ENTRY_SECONDS / 60)} minutes before the scheduled time.
          </p>
        </div>
      </div>
    );
  }

  // Early entry state - waiting for interviewer
  if (viewState === 'EARLY_ENTRY') {
    return (
      <div className="interview-room early-entry">
        <WaitingScreen
          candidateName={roomState.candidate_name}
          secondsRemaining={roomState.seconds_remaining}
        />
      </div>
    );
  }

  // Active interview state
  if (viewState === 'ACTIVE' || viewState === 'READY') {
    if (!isAIOptedIn) {
      return (
        <PreJoinScreen
          roomState={roomState}
          onJoin={() => setIsAIOptedIn(true)}
        />
      );
    }

    return (
      <div style={{
        backgroundColor: '#1a202c', height: '100vh', display: 'flex', flexDirection: 'column',
        fontFamily: "'Inter', sans-serif", color: 'white', overflow: 'hidden'
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 32px', borderBottom: '1px solid #2d3748', backgroundColor: '#2d3748'
        }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>{roomState.company} - {roomState.job_role}</h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#a0aec0' }}>Candidate: {roomState.candidate_name}</p>
          </div>

          <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
            <div style={{ color: '#e2e8f0', fontSize: '14px', background: 'rgba(0,0,0,0.2)', padding: '6px 16px', borderRadius: '15px', fontWeight: '500' }}>
              Progress: Question {Math.max(1, Math.floor(messages.filter(m => m && m.speaker && m.speaker.toLowerCase() === 'ai').length))} of ~5
            </div>
          </div>

          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '20px' }}>
            <VoiceIndicator isAISpeaking={isAISpeaking} />
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              backgroundColor: '#1a202c', padding: '6px 16px', borderRadius: '20px',
              border: '1px solid #4a5568'
            }}>
              <span style={{
                width: '8px', height: '8px', backgroundColor: '#48bb78',
                borderRadius: '50%', display: 'inline-block'
              }} />
              <span style={{ fontSize: '14px', fontWeight: '500', color: '#e2e8f0' }}>Live</span>
              <ActiveTimer />
            </div>
          </div>
        </div>

        {/* Main Content Area */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative' }}>
          
          {/* Floating Diagnostic Dashboard (Visible in Active room) */}
          <div className="diagnostic-badge" style={{
            position: 'absolute',
            top: '20px',
            right: '20px',
            zIndex: 100,
            background: 'rgba(0,0,0,0.6)',
            backdropFilter: 'blur(5px)',
            padding: '8px 12px',
            borderRadius: '12px',
            fontSize: '11px',
            color: 'white',
            display: 'flex',
            gap: '15px',
            border: '1px solid rgba(255,255,255,0.1)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <div style={{ 
                width: '8px', 
                height: '8px', 
                borderRadius: '50%', 
                background: micActive ? '#4ade80' : '#64748b',
                boxShadow: micActive ? '0 0 8px #4ade80' : 'none'
              }}></div>
              <span>Mic: {micActive ? 'CAPTURING' : 'IDLE'}</span>
            </div>
            <div style={{ borderLeft: '1px solid rgba(255,255,255,0.2)', paddingLeft: '15px' }}>
              <span>Out: {(bytesSent / 1024).toFixed(1)} KB</span>
            </div>
          </div>

          {/* Left Sidebar: Transcript + Text Input (Priya's pattern) */}
          <div style={{
            flex: '1', maxWidth: '400px', borderRight: '1px solid #2d3748',
            display: 'flex', flexDirection: 'column', backgroundColor: '#1e293b',
            overflow: 'hidden'
          }}>
            <div style={{ padding: '16px', borderBottom: '1px solid #2d3748', fontWeight: '600', color: '#e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
              <span>Live Transcript</span>
              <span style={{ fontSize: '12px', color: '#a0aec0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '8px', height: '8px', backgroundColor: '#48bb78', borderRadius: '50%', animation: 'pulse 2s infinite' }}></span>
                Recording
              </span>
            </div>

            {/* VAD INDICATOR showing candidate when mic is active and speech detected */}
            <div style={{
              height: '24px', backgroundColor: '#0f172a', borderBottom: '1px solid #2d3748',
              display: 'flex', alignItems: 'center', padding: '0 16px', fontSize: '11px', color: '#94a3b8', flexShrink: 0
            }}>
              {!isAISpeaking ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {micLevel > 4 ? (
                    <>
                      <span style={{ width: '6px', height: '6px', backgroundColor: '#38bdf8', borderRadius: '50%', boxShadow: '0 0 8px #38bdf8' }} />
                      Detecting speech...
                    </>
                  ) : (
                    <>
                      <span style={{ width: '6px', height: '6px', backgroundColor: '#64748b', borderRadius: '50%' }} />
                      Listening for you to speak
                    </>
                  )}
                </span>
              ) : (
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#f59e0b' }}>
                  <span style={{ width: '6px', height: '6px', backgroundColor: '#f59e0b', borderRadius: '50%' }} />
                  AI is speaking
                </span>
              )}
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
              <ChatInterface messages={messages} />
            </div>
            {/* Priya: "Always fall back to text." — permanent text input */}
            <div style={{ padding: '12px 16px', borderTop: '1px solid #2d3748', display: 'flex', gap: '8px', flexShrink: 0 }}>
              <input
                type="text"
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleManualSend(); }}
                placeholder="Type your answer here..."
                style={{
                  flex: 1, padding: '10px 14px', borderRadius: '8px',
                  backgroundColor: '#0f172a', border: '1px solid #4a5568',
                  color: 'white', fontSize: '14px', outline: 'none'
                }}
              />
              <button
                onClick={handleManualSend}
                disabled={manualText.trim().length === 0}
                style={{
                  padding: '10px 16px', borderRadius: '8px',
                  backgroundColor: manualText.trim().length > 0 ? '#3182ce' : '#2d3748',
                  color: 'white', border: 'none',
                  cursor: manualText.trim().length > 0 ? 'pointer' : 'not-allowed',
                  fontWeight: '500', fontSize: '14px'
                }}
              >
                Send
              </button>
            </div>
          </div>

          {/* Center Area: AI Focus */}
          <div style={{ flex: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px' }}>
            {/* AI Avatar */}
            <div style={{
              width: '200px', height: '200px', borderRadius: '50%',
              background: isAISpeaking ? 'radial-gradient(circle, #3182ce 0%, #2b6cb0 50%, #1a365d 100%)' : '#2d3748',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: isAISpeaking ? '0 0 40px rgba(49, 130, 206, 0.4)' : 'none',
              transition: 'all 0.3s ease-in-out', marginBottom: '40px',
              animation: isAISpeaking ? 'avatarPulse 1.5s infinite' : 'none'
            }}>
              <span style={{ fontSize: '64px' }}>🤖</span>
            </div>

            <div style={{ textAlign: 'center', maxWidth: '600px' }}>
              <h3 style={{ margin: '0 0 10px 0', fontSize: '24px', color: '#e2e8f0', fontWeight: '600' }}>{roomState.interviewer_designation}</h3>
              <p style={{
                fontSize: '18px', color: '#a0aec0', lineHeight: '1.6',
                backgroundColor: '#2d3748', padding: '20px', borderRadius: '12px'
              }}>
                {isAISpeaking ? "AI is speaking..." : "AI is listening to your response..."}
              </p>
              {/* Mic Level Indicator — helps verify the mic is working */}
              {!isAISpeaking && (
                <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '5px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', justifyContent: 'center', width: '100%' }}>
                    <span style={{ fontSize: '13px', color: '#a0aec0' }}>🎙️ Level:</span>
                    <div style={{ width: '180px', height: '10px', backgroundColor: '#1a202c', borderRadius: '5px', overflow: 'hidden', position: 'relative' }}>
                      {/* Threshold Marker */}
                      <div style={{ 
                        position: 'absolute', left: `${3 * 3.3}%`, top: 0, bottom: 0, width: '2px', 
                        backgroundColor: 'rgba(255,255,255,0.4)', zIndex: 2 
                      }} title="VAD Threshold" />
                      
                      <div style={{
                        width: `${Math.min(micLevel * 3.3, 100)}%`,
                        height: '100%',
                        backgroundColor: micLevel > 3 ? '#48bb78' : micLevel > 1.5 ? '#ecc94b' : '#e53e3e',
                        borderRadius: '4px',
                        transition: 'width 0.1s ease'
                      }} />
                    </div>
                  </div>
                  <div style={{ fontSize: '11px', color: '#718096', display: 'flex', gap: '15px' }}>
                    <span>VAD Status: <strong style={{ color: isSpeakingRef.current ? '#48bb78' : '#cbd5e0' }}>{isSpeakingRef.current ? 'SENDING' : speechStartRef.current ? 'HEARING' : 'IDLE'}</strong></span>
                    <span>Level: <strong>{micLevel.toFixed(1)}</strong></span>
                  </div>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* CSS for animations */}
        <style dangerouslySetInnerHTML={{
          __html: `
          @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(72, 187, 120, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(72, 187, 120, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(72, 187, 120, 0); }
          }
          @keyframes avatarPulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(49, 130, 206, 0.7); }
            70% { transform: scale(1.05); box-shadow: 0 0 0 20px rgba(49, 130, 206, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(49, 130, 206, 0); }
          }
        `}} />

        {/* Footer Controls */}
        <div style={{
          padding: '24px', borderTop: '1px solid #2d3748', backgroundColor: '#1e293b',
          display: 'flex', justifyContent: 'center', gap: '20px'
        }}>
          <button style={{
            padding: '12px 32px', fontSize: '16px', fontWeight: '500',
            backgroundColor: 'rgba(255, 255, 255, 0.1)', color: 'white',
            border: '1px solid #4a5568', borderRadius: '8px', cursor: 'grabbed'
          }}>
            🎙️ Unmuted
          </button>

          <button
            onClick={() => {
              if (window.confirm("Are you sure you want to end this interview early?")) {
                window.location.href = '/';
              }
            }}
            style={{
              padding: '12px 32px', fontSize: '16px', fontWeight: '500',
              backgroundColor: '#e53e3e', color: 'white', border: 'none',
              borderRadius: '8px', cursor: 'pointer', transition: 'background-color 0.2s'
            }}
            onMouseOver={(e) => e.target.style.backgroundColor = '#c53030'}
            onMouseOut={(e) => e.target.style.backgroundColor = '#e53e3e'}
          >
            Leave Interview
          </button>
        </div>
      </div >
    );
  }

  // Completed state
  if (viewState === 'COMPLETED') {
    return (
      <div className="interview-room completed">
        <div className="completion-message">
          <div className="success-icon">✓</div>
          <h2>Interview Completed</h2>
          <p>Thank you for your time, {roomState.candidate_name}!</p>
          <p className="completion-details">
            Your interview has been successfully completed.
            The evaluation report will be sent to the administrator.
          </p>
          <p className="next-steps">
            You will be contacted regarding the next steps in the hiring process.
          </p>
        </div>
      </div>
    );
  }

  // Expired state
  if (viewState === 'EXPIRED') {
    return (
      <div className="interview-room expired">
        <div className="expired-message">
          <div className="warning-icon">⏰</div>
          <h2>Session Expired</h2>
          <p>This interview session has expired.</p>
          <p className="expired-details">
            The interview window has closed. Please contact the administrator
            if you need to reschedule.
          </p>
        </div>
      </div>
    );
  }

  // Cancelled state
  if (viewState === 'CANCELLED') {
    return (
      <div className="interview-room cancelled">
        <div className="cancelled-message">
          <div className="info-icon">ℹ️</div>
          <h2>Interview Cancelled</h2>
          <p>This interview has been cancelled.</p>
          <p className="cancelled-details">
            Please contact the administrator for more information.
          </p>
        </div>
      </div>
    );
  }

  // Reconnecting / Transitioning fallback UI
  // FAILURE MODES CONSIDERED:
  // 1. Unhandled Status: Shows a premium loading indicator instead of white screen.
  // 2. DISCONNECTED: The UI maintains the room layout or shows this transition if roomState is lost.
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100vh', backgroundColor: '#1a202c', color: 'white', fontFamily: "'Inter', sans-serif",
      background: 'radial-gradient(circle at center, #1e293b 0%, #0f172a 100%)'
    }}>
      <div style={{
        padding: '40px', borderRadius: '24px', backgroundColor: 'rgba(255, 255, 255, 0.03)',
        backdropFilter: 'blur(12px)', border: '1px solid rgba(255, 255, 255, 0.1)',
        textAlign: 'center', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{
          width: '64px', height: '64px', border: '3px solid rgba(49, 130, 206, 0.2)',
          borderTopColor: '#3182ce', borderRadius: '50%', animation: 'spin 1s linear infinite',
          margin: '0 auto 24px auto'
        }} />
        <h2 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '8px', color: '#e2e8f0' }}>
          {roomState?.status === 'DISCONNECTED' ? 'Reconnecting...' : 'Syncing Interview State...'}
        </h2>
        <p style={{ color: '#94a3b8', fontSize: '14px' }}>
          {roomState?.status === 'DISCONNECTED' 
            ? 'Your connection was interrupted. We are trying to restore your session.' 
            : 'Please wait while we prepare your room.'}
        </p>
      </div>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes spin { to { transform: rotate(360deg); } }
      `}} />
    </div>
  );
};

export default InterviewRoom;
