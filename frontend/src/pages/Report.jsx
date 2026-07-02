import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getEvaluationReport } from '../services/api';
import './Report.css'; // Importing the premium styles

export default function Report() {
  const { roomId } = useParams();
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const data = await getEvaluationReport(roomId);
        if (data.success) {
          setReportData(data.evaluation);
        } else {
          setError(data.error || "Failed to load report.");
        }
      } catch (err) {
        setError(err.message || "Network error fetching report.");
      } finally {
        setLoading(false);
      }
    };

    fetchReport();
  }, [roomId]);

  if (loading) return <div className="report-loading">Loading evaluation report...</div>;
  if (error) return <div className="report-error">Error: {error}</div>;
  if (!reportData) return <div className="report-empty">No report found for this session. Did it complete?</div>;

  // Derive score class
  let scoreClass = 'score-poor';
  if (reportData.overall_score >= 7) scoreClass = 'score-excellent';
  else if (reportData.overall_score >= 5) scoreClass = 'score-average';

  return (
    <main className="report-container">
      <header className="report-header">
        <h1 className="report-title">Interview Report</h1>
        <Link to="/" className="btn-back">
          ← Back to Dashboard
        </Link>
      </header>

      <section className="candidate-card">
        <h2>Candidate Profile</h2>
        <div className="candidate-info-grid">
          <div className="info-item">
            <span className="info-label">Name</span>
            <span className="info-value">{reportData.candidate_name}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Role</span>
            <span className="info-value">{reportData.job_role}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Company</span>
            <span className="info-value">{reportData.company}</span>
          </div>
          <div className="info-item">
            <span className="info-label">Date Completed</span>
            <span className="info-value">{new Date(reportData.completed_at || reportData.scheduled_at).toLocaleDateString()}</span>
          </div>
        </div>
      </section>

      <section className="score-section">
        <div className="overall-score-card">
          <h3>Overall Score</h3>
          <div className={`score-value ${scoreClass}`}>
            {reportData.overall_score.toFixed(1)}<span className="sub-score-max">/10</span>
          </div>
        </div>

        <div className="sub-scores-grid">
          <div className="sub-score-item">
            <span className="sub-score-label">Technical</span>
            <span className="sub-score-number">{reportData.technical_score}<span className="sub-score-max">/10</span></span>
          </div>
          <div className="sub-score-item">
            <span className="sub-score-label">Communication</span>
            <span className="sub-score-number">{reportData.communication_score}<span className="sub-score-max">/10</span></span>
          </div>
          <div className="sub-score-item">
            <span className="sub-score-label">Problem Solving</span>
            <span className="sub-score-number">{reportData.problem_solving_score}<span className="sub-score-max">/10</span></span>
          </div>
          <div className="sub-score-item">
            <span className="sub-score-label">Behavioral</span>
            <span className="sub-score-number">{reportData.behavioral_score}<span className="sub-score-max">/10</span></span>
          </div>
          <div className="sub-score-item" style={{ gridColumn: '1 / -1' }}>
            <span className="sub-score-label">Confidence</span>
            <span className="sub-score-number">{reportData.confidence_score}<span className="sub-score-max">/10</span></span>
          </div>
        </div>
      </section>

      {reportData.criteria_reasoning && Object.keys(reportData.criteria_reasoning).length > 0 && (
        <section className="reasoning-card">
          <h2>Detailed Assessment</h2>
          <div className="reasoning-grid">
            {[
              { key: 'technical', label: 'Technical', score: reportData.technical_score },
              { key: 'communication', label: 'Communication', score: reportData.communication_score },
              { key: 'problem_solving', label: 'Problem Solving', score: reportData.problem_solving_score },
              { key: 'behavioral', label: 'Behavioral', score: reportData.behavioral_score },
              { key: 'confidence', label: 'Confidence', score: reportData.confidence_score },
            ].map(({ key, label, score }) => {
              const bullets = reportData.criteria_reasoning[key];
              if (!bullets || bullets.length === 0) return null;
              return (
                <div className="reasoning-item" key={key}>
                  <div className="reasoning-item-header">
                    <span className="reasoning-label">{label}</span>
                    <span className="reasoning-score">{Number(score).toFixed(1)}/10</span>
                  </div>
                  <ul className="reasoning-bullets">
                    {bullets.map((b, i) => <li key={i}>{b}</li>)}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="feedback-card">
        <h2>
          {/* Subtle icon placeholder */}
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#3b82f6' }}>
            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
          </svg>
          Qualitative Feedback
        </h2>
        <div className="feedback-content">
          {reportData.qualitative_feedback}
        </div>
      </section>

      {reportData.report_path && (
        <footer className="report-footer">
          <div className="pdf-note">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            A PDF version of this report has been safely generated and emailed to the admin.
          </div>
        </footer>
      )}
    </main>
  );
}
