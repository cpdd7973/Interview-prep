import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listInterviews, scheduleInterview, cancelInterview } from '../services/api';

export default function Dashboard() {
  const [interviews, setInterviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentTab, setCurrentTab] = useState('PENDING'); // PENDING, ACTIVE, COMPLETED

  // Form state
  const [formData, setFormData] = useState({
    candidate_email: '',
    candidate_name: '',
    job_role: '',
    company: '',
    interviewer_designation: '',
    scheduled_at: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchInterviews = async () => {
    setLoading(true);
    try {
      const data = await listInterviews(currentTab);
      if (data.success) {
        setInterviews(data.sessions || []);
      } else {
        setError(data.error || "Failed to load interviews.");
      }
    } catch (err) {
      setError(err.message || "Network error while fetching interviews.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInterviews();
  }, [currentTab]);

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleScheduleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      // Create UTC iso string from local datetime-local input
      const dateObj = new Date(formData.scheduled_at);

      if (dateObj.getTime() < Date.now()) {
        setError("Cannot schedule an interview in the past.");
        setIsSubmitting(false);
        return;
      }

      const payload = { ...formData, scheduled_at: dateObj.toISOString() };

      const res = await scheduleInterview(payload);
      if (res.success) {
        setFormData({
          candidate_email: '', candidate_name: '', job_role: '',
          company: '', interviewer_designation: '', scheduled_at: ''
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

  const handleCancel = async (roomId) => {
    if (!window.confirm("Are you sure you want to cancel this interview?")) return;
    try {
      const res = await cancelInterview(roomId);
      if (res.success) {
        fetchInterviews();
      } else {
        alert(res.error || "Failed to cancel.");
      }
    } catch (err) {
      alert("Error cancelling interview.");
    }
  };

  return (
    <div className="container" style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <h1>Interview Agent Dashboard</h1>

      {error && <div style={{ color: 'red', padding: '10px', border: '1px solid red', marginBottom: '20px' }}>{error}</div>}

      <div style={{ display: 'flex', gap: '40px' }}>
        {/* Left Side: Schedule Form */}
        <div style={{ flex: '1', backgroundColor: '#f9f9f9', padding: '20px', borderRadius: '8px' }}>
          <h2>Schedule New Interview</h2>
          <form onSubmit={handleScheduleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <input name="candidate_name" placeholder="Candidate Name" value={formData.candidate_name} onChange={handleInputChange} required />
            <input name="candidate_email" type="email" placeholder="Candidate Email" value={formData.candidate_email} onChange={handleInputChange} required />
            <input name="job_role" placeholder="Job Role (e.g., Frontend Developer)" value={formData.job_role} onChange={handleInputChange} required />
            <input name="company" placeholder="Company Name" value={formData.company} onChange={handleInputChange} required />
            <input name="interviewer_designation" placeholder="Interviewer Title (e.g., Senior Engineer)" value={formData.interviewer_designation} onChange={handleInputChange} required />
            <input
              name="scheduled_at"
              type="datetime-local"
              value={formData.scheduled_at}
              onChange={handleInputChange}
              min={new Date().toISOString().slice(0, 16)}
              required
            />

            <button type="submit" disabled={isSubmitting} style={{ padding: '10px', background: '#007BFF', color: '#FFF', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
              {isSubmitting ? 'Scheduling...' : 'Schedule Interview'}
            </button>
          </form>
        </div>

        {/* Right Side: Interview List */}
        <div style={{ flex: '2' }}>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
            {['PENDING', 'ACTIVE', 'COMPLETED'].map(tab => (
              <button
                key={tab}
                onClick={() => setCurrentTab(tab)}
                style={{
                  padding: '10px 20px',
                  background: currentTab === tab ? '#007BFF' : '#EEE',
                  color: currentTab === tab ? '#FFF' : '#333',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {loading ? (
            <p>Loading interviews...</p>
          ) : interviews.length === 0 ? (
            <p>No {currentTab.toLowerCase()} interviews found.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
              {interviews.map(i => {
                const isPastLimit = new Date(i.scheduled_at).getTime() + 60 * 60 * 1000 < Date.now();
                return (
                  <div key={i.room_id} style={{ padding: '15px', border: '1px solid #CCC', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <strong>{i.candidate_name}</strong> - {i.job_role} <br />
                      <small>{new Date(i.scheduled_at).toLocaleString()}</small>
                      {isPastLimit && currentTab === 'PENDING' && <span style={{ color: 'red', marginLeft: '10px' }}>(Expired)</span>}
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                      {currentTab === 'PENDING' && (
                        <button onClick={() => handleCancel(i.room_id)} style={{ padding: '5px 10px', background: 'red', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
                          Cancel
                        </button>
                      )}
                      {currentTab === 'COMPLETED' && (
                        <Link to={`/report/${i.room_id}`} style={{ padding: '5px 10px', background: '#28a745', color: 'white', textDecoration: 'none', borderRadius: '4px' }}>
                          View Report
                        </Link>
                      )}
                      {!(isPastLimit && currentTab === 'PENDING') && (
                        <Link to={`/interview/${i.room_id}`} style={{ padding: '5px 10px', background: '#17a2b8', color: 'white', textDecoration: 'none', borderRadius: '4px' }}>
                          Go to Room
                        </Link>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
