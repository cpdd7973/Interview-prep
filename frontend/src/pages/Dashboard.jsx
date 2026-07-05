import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listInterviews, scheduleInterview, cancelInterview } from '../services/api';
import { useAuth } from '../context/AuthContext';
import './Dashboard.css';

export default function Dashboard() {
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentTab, setCurrentTab] = useState('PENDING'); // PENDING, ACTIVE, COMPLETED
  const [confirmingCancelRoomId, setConfirmingCancelRoomId] = useState(null);
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Form state
  const [formData, setFormData] = useState({
    candidate_email: '',
    candidate_name: '',
    job_role: '',
    company: '',
    interviewer_designation: '',
    job_description: '',
    scheduled_at: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    fetchInterviews();
    // Poll every 30s
    const interval = setInterval(fetchInterviews, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchInterviews = async () => {
    try {
      const res = await listInterviews();
      if (res.success) {
        setInterviews(res.sessions || []);
      } else {
        setError(res.error || "Failed to fetch interviews.");
      }
    } catch (err) {
      setError("Network or API error.");
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleScheduleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      // dateObj will correctly represent the LOCAL datetime selected
      const dateObj = new Date(formData.scheduled_at);

      if (dateObj.getTime() < Date.now() - 60000) { // Allow 1m grace
        setError("Cannot schedule an interview in the past.");
        setIsSubmitting(false);
        return;
      }

      // Ensure we send it as a strict UTC ISO string ending in Z
      const payload = { ...formData, scheduled_at: dateObj.toISOString() };

      const res = await scheduleInterview(payload);
      if (res.success) {
        setFormData({
          candidate_email: '', candidate_name: '', job_role: '',
          company: '', interviewer_designation: '', job_description: '', scheduled_at: ''
        });
        if (currentTab === 'PENDING') fetchInterviews();
        else setCurrentTab('PENDING');
      } else {
        setError(res.error || "Failed to schedule interview.");
      }
    } catch (err) {
      setError(err.message || "Error scheduling interview.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelClick = async (roomId) => {
    if (confirmingCancelRoomId === roomId) {
      console.log(`[DASHBOARD] 🚫 Confirmed cancel for: ${roomId}`);
      try {
        const res = await cancelInterview(roomId);
        if (res.success) {
          setConfirmingCancelRoomId(null);
          fetchInterviews();
        } else {
          alert(res.error || "Failed to cancel.");
        }
      } catch (err) {
        alert("Error cancelling interview.");
      }
    } else {
      setConfirmingCancelRoomId(roomId);
      // Reset after 3 seconds
      setTimeout(() => setConfirmingCancelRoomId(null), 3000);
    }
  };

  const tabs = ['PENDING', 'ACTIVE', 'EXPIRED', 'COMPLETED'];

  const filteredInterviews = interviews.filter(i => {
    if (currentTab === 'PENDING') return i.status === 'PENDING';
    if (currentTab === 'ACTIVE') return ['ACTIVE', 'DISCONNECTED', 'EVALUATION_FAILED', 'REPORT_FAILED'].includes(i.status) || (i.status === 'COMPLETED' && !i.report_generated_at);
    if (currentTab === 'EXPIRED') return i.status === 'EXPIRED';
    if (currentTab === 'COMPLETED') return i.status === 'COMPLETED' && i.report_generated_at !== null;
    return true;
  });

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <div className="header-top-bar">
          <h1>Interview Prep</h1>
          {user && (
            <div className="user-bar">
              {user.picture ? (
                <img src={user.picture} alt={user.name} className="user-avatar" referrerPolicy="no-referrer" />
              ) : (
                <div className="user-avatar-fallback">{user.name?.charAt(0)?.toUpperCase() || '?'}</div>
              )}
              <span className="user-name">{user.name}</span>
              <button className="btn-logout" onClick={logout} title="Sign out">↗ Sign out</button>
            </div>
          )}
        </div>
        <p>Your comprehensive workspace for orchestrating AI-driven technical assessments. Effortlessly schedule interviews, monitor candidate progress in real-time, and access deep-dive analytics to streamline your hiring pipeline.</p>
      </div>

      {error && <div className="global-error">
        <span>⚠️</span> {error}
      </div>}

      <div className="dashboard-grid">
        {/* Left Side: Schedule Form */}
        <div className="schedule-card">
          <h2>Schedule Interview</h2>
          <form onSubmit={handleScheduleSubmit}>
            <div className="form-grid">
              <div className="form-group">
                <label>👤 Candidate Name</label>
                <input name="candidate_name" className="form-input" placeholder="e.g. John Doe" value={formData.candidate_name} onChange={handleInputChange} required />
              </div>

              <div className="form-group">
                <label>📧 Candidate Email</label>
                <input name="candidate_email" type="email" className="form-input" placeholder="john@example.com" value={formData.candidate_email} onChange={handleInputChange} required />
              </div>

              <div className="form-group">
                <label>💻 Job Role</label>
                <input name="job_role" className="form-input" placeholder="e.g. Frontend Developer" value={formData.job_role} onChange={handleInputChange} required />
              </div>

              <div className="form-group">
                <label>🏢 Company</label>
                <input name="company" className="form-input" placeholder="e.g. Acme Corp" value={formData.company} onChange={handleInputChange} required />
              </div>

              <div className="form-group">
                <label>🎓 Interviewer</label>
                <input name="interviewer_designation" className="form-input" placeholder="e.g. Senior Engineer" value={formData.interviewer_designation} onChange={handleInputChange} required />
              </div>

              <div className="form-group">
                <label>🕒 Date & Time</label>
                <input
                  name="scheduled_at"
                  type="datetime-local"
                  className="form-input"
                  value={formData.scheduled_at}
                  onChange={handleInputChange}
                  min={new Date(new Date().getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)}
                  required
                />
              </div>
            </div>

            {/* Note: Outside form-grid to stretch full width */}
            <div className="form-group full-width" style={{ marginTop: '1rem', marginBottom: '1.5rem' }}>
              <label>📝 Optional: Paste Job Description</label>
              <textarea
                name="job_description"
                className="form-input"
                placeholder="Paste the job description here to help the AI interviewer generate role-specific questions..."
                value={formData.job_description}
                onChange={handleInputChange}
                rows={5}
                style={{ resize: 'vertical', minHeight: '100px' }}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <span className="spinner-small"></span>
                  Scheduling...
                </>
              ) : (
                'Confirm & Schedule'
              )}
            </button>
          </form>
        </div>

        {/* Right Side: Interview List */}
        <div>
          <div className="tabs-container">
            {tabs.map(tab => {
              const count = interviews.filter(i => {
                if (tab === 'PENDING') return i.status === 'PENDING';
                if (tab === 'ACTIVE') return ['ACTIVE', 'DISCONNECTED', 'EVALUATION_FAILED', 'REPORT_FAILED'].includes(i.status) || (i.status === 'COMPLETED' && !i.report_generated_at);
                if (tab === 'EXPIRED') return i.status === 'EXPIRED';
                if (tab === 'COMPLETED') return i.status === 'COMPLETED' && i.report_generated_at !== null;
                return false;
              }).length;

              return (
                <button
                  key={tab}
                  onClick={() => setCurrentTab(tab)}
                  className={`tab-btn ${currentTab === tab ? 'active' : ''}`}
                >
                  {tab.charAt(0) + tab.slice(1).toLowerCase()} ({count})
                </button>
              );
            })}
          </div>

          {loading ? (
            <div className="empty-state">
              <div className="spinner-small" style={{ margin: '0 auto 16px' }}></div>
              Loading interviews...
            </div>
          ) : filteredInterviews.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                {currentTab === 'PENDING' ? '📅' : currentTab === 'ACTIVE' ? '🎙️' : '📋'}
              </div>
              <p>No {currentTab.toLowerCase()} interviews found.</p>
              <p style={{ fontSize: '14px', marginTop: '4px' }}>New scheduled sessions will appear here.</p>
            </div>
          ) : (
            <div className="interview-list">
              {filteredInterviews.map(i => (
                <InterviewCard
                  key={i.room_id}
                  interview={i}
                  currentTab={currentTab}
                  handleCancel={handleCancelClick}
                  isConfirming={confirmingCancelRoomId === i.room_id}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Subcomponent to manage live timers per card
function InterviewCard({ interview, currentTab, handleCancel, isConfirming }) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let timer;
    if (currentTab === 'PENDING' || interview.status === 'DISCONNECTED') {
      timer = setInterval(() => setNow(Date.now()), 1000);
    }
    return () => clearInterval(timer);
  }, [currentTab, interview.status]);

  const scheduledTime = new Date(interview.scheduled_at).getTime();
  const disconnectedTime = interview.disconnected_at ? new Date(interview.disconnected_at).getTime() : null;

  const formatTimeLeft = (ms) => {
    if (ms <= 0) return "00:00";
    const m = Math.floor(ms / 60000).toString().padStart(2, '0');
    const s = Math.floor((ms % 60000) / 1000).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  let UIStatus = null;
  let interactive = true;

  // Render logic per tab configuration
  if (currentTab === 'PENDING') {
    const expiresAt = scheduledTime + (15 * 60 * 1000);
    const msLeft = expiresAt - now;
    const isCritical = msLeft < (3 * 60 * 1000);

    // Only show live countdown if we are past the scheduled time (or within 15 min buffer)
    if (now >= scheduledTime && msLeft > 0) {
      UIStatus = <span style={{ color: isCritical ? '#ef4444' : '#f59e0b', fontWeight: 600, fontSize: '0.875rem' }}>⏳ Expires in {formatTimeLeft(msLeft)}</span>;
    } else if (now < scheduledTime) {
      UIStatus = <span className="status-badge pending">PENDING</span>;
    } else {
      UIStatus = <span className="status-badge expired">EXPIRED</span>;
    }
  }
  else if (currentTab === 'ACTIVE') {
    if (interview.status === 'DISCONNECTED' && disconnectedTime) {
      const reconnectDeadline = disconnectedTime + (15 * 60 * 1000);
      const msLeft = reconnectDeadline - now;
      UIStatus = <span style={{ color: '#f59e0b', fontWeight: 600, fontSize: '0.875rem' }}>⚠️ Reconnecting... {formatTimeLeft(msLeft)}</span>;
    } else if (interview.status === 'EVALUATION_FAILED') {
      UIStatus = <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.875rem' }}>⚠️ Evaluation Failed</span>;
      interactive = false;
    } else if (interview.status === 'REPORT_FAILED') {
      UIStatus = <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.875rem' }}>⚠️ Report Failed</span>;
      interactive = false;
    } else if (interview.report_retry_count >= 3 && interview.finished_at) {
      UIStatus = <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.875rem' }}>⚠️ Report Failed</span>;
      interactive = false;
    } else if (interview.finished_at || interview.status === 'COMPLETED') {
      UIStatus = <span style={{ color: '#3b82f6', fontWeight: 600, fontSize: '0.875rem' }}>⚙️ Generating Report...</span>;
      interactive = false;
    } else {
      UIStatus = <span style={{ color: '#10b981', fontWeight: 600, fontSize: '0.875rem', display: 'flex', alignItems: 'center', gap: '4px' }}><span className="pulse-dot"></span> In Progress</span>;
    }
  }
  else if (currentTab === 'EXPIRED') {
    UIStatus = <span style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.875rem' }}>Expired — never joined</span>;
    interactive = false;
  }
  else if (currentTab === 'COMPLETED') {
    UIStatus = <span className="status-badge completed">✅ Report Ready</span>;
  }

  // Ensure ISO string is treated as UTC (append Z if missing)
  const isoStr = interview.scheduled_at?.endsWith('Z') || interview.scheduled_at?.includes('+')
    ? interview.scheduled_at
    : `${interview.scheduled_at}Z`;

  const scheduledDate = new Date(isoStr);
  const cardScheduledTime = scheduledDate.getTime();
  const isUpcoming = cardScheduledTime > now;

  return (
    <div className={`interview-card ${isUpcoming ? 'upcoming' : ''}`}>
      <div className="interview-info">
        <h3>{interview.candidate_name} <span className="role-text">for {interview.job_role}</span></h3>
        <div className="interview-meta">
          <span>{scheduledDate.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })} at {scheduledDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          {interview.status === 'EXPIRED' && <span className="badge expired">EXPIRED</span>}
          {interview.status === 'PENDING' && !isUpcoming && <span className="badge starting">STARTING NOW</span>}
        </div>
      </div>
      <div className="card-actions">
        {currentTab === 'PENDING' && (
          <button 
            onClick={() => handleCancel(interview.room_id)} 
            className={isConfirming ? "btn-warning" : "btn-danger"}
            style={{ transition: 'all 0.2s', fontWeight: isConfirming ? 'bold' : 'normal' }}
          >
            {isConfirming ? "Confirm Cancel?" : "Cancel"}
          </button>
        )}
        {currentTab === 'COMPLETED' && (
          <Link to={`/report/${interview.room_id}`} className="btn-success">
            View Report
          </Link>
        )}
        {['PENDING', 'ACTIVE'].includes(currentTab) && interactive && (
          <Link to={`/interview/${interview.room_id}`} className="btn-primary-small">
            Enter Room
          </Link>
        )}
      </div>
    </div>
  );
}
