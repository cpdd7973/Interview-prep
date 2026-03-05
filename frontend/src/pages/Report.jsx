import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getEvaluationReport } from '../services/api';

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

  if (loading) return <div style={{ padding: '20px' }}>Loading evaluation report...</div>;
  if (error) return <div style={{ padding: '20px', color: 'red' }}>Error: {error}</div>;
  if (!reportData) return <div style={{ padding: '20px' }}>No report found for this session. Did it complete?</div>;

  return (
    <div className="container" style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1>Interview Report</h1>
        <Link to="/" style={{ padding: '10px 15px', background: '#6c757d', color: '#FFF', textDecoration: 'none', borderRadius: '4px' }}>
          Back to Dashboard
        </Link>
      </div>

      <div style={{ backgroundColor: '#f8f9fa', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <h2>Candidate Info</h2>
        <p><strong>Name:</strong> {reportData.candidate_name}</p>
        <p><strong>Role:</strong> {reportData.job_role} at {reportData.company}</p>
        <p><strong>Date:</strong> {new Date(reportData.completed_at || reportData.scheduled_at).toLocaleString()}</p>
      </div>

      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
        <div style={{ flex: 1, backgroundColor: '#e9ecef', padding: '20px', borderRadius: '8px', textAlign: 'center' }}>
          <h3>Overall Score</h3>
          <h1 style={{ color: reportData.overall_score >= 7 ? '#28a745' : reportData.overall_score >= 5 ? '#ffc107' : '#dc3545', fontSize: '3rem', margin: '10px 0' }}>
            {reportData.overall_score.toFixed(1)} / 10
          </h1>
        </div>

        <div style={{ flex: 2, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
          <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <strong>Technical:</strong> {reportData.technical_score}/10
          </div>
          <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <strong>Communication:</strong> {reportData.communication_score}/10
          </div>
          <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <strong>Problem Solving:</strong> {reportData.problem_solving_score}/10
          </div>
          <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <strong>Behavioral:</strong> {reportData.behavioral_score}/10
          </div>
          <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: '4px' }}>
            <strong>Confidence:</strong> {reportData.confidence_score}/10
          </div>
        </div>
      </div>

      <div style={{ backgroundColor: '#fff', border: '1px solid #dee2e6', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
        <h2>Qualitative Feedback</h2>
        <div style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
          {reportData.qualitative_feedback}
        </div>
      </div>

      {reportData.report_path && (
        <div style={{ textAlign: 'center', marginTop: '30px' }}>
          <p style={{ color: '#6c757d' }}>A PDF version of this report has been generated and emailed to the admin.</p>
        </div>
      )}
    </div>
  );
}
