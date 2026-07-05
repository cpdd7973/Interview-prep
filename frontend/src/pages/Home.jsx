import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import Dashboard from './Dashboard';
import './Home.css';

const STEPS = [
  { icon: '📅', title: 'Schedule', text: 'Add a candidate, paste the job description, and pick a time — the AI interviewer prepares role-specific questions automatically.' },
  { icon: '🎙️', title: 'AI Interview', text: 'The candidate joins with just a link. A live AI panel conducts a voice-driven technical interview in real time.' },
  { icon: '📊', title: 'Get Report', text: 'Once the session ends, an evaluator agent scores the transcript and generates a detailed candidate report.' },
];

const FEATURES = [
  { icon: '🧠', title: 'JD-aware questions', text: 'Questions are tailored to the specific role and job description, not a generic bank.' },
  { icon: '🗣️', title: 'Real-time voice interview', text: 'Natural, spoken conversation — no typing required from the candidate.' },
  { icon: '📈', title: 'Automated scoring & reports', text: 'Consistent, structured evaluation with a shareable report at the end.' },
  { icon: '🔒', title: 'Secure, link-based access', text: 'Candidates join with a single private room link — no account needed.' },
];

export default function Home() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        fontFamily: "'Inter', sans-serif",
        color: '#64748B',
        fontSize: '16px',
        gap: '12px',
      }}>
        <div className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }}></div>
        Loading...
      </div>
    );
  }

  if (user) {
    return <Dashboard />;
  }

  return (
    <div className="home-page">
      <header className="home-topbar">
        <div className="home-logo">🎙️ Interview Prep</div>
        <Link to="/login" className="btn-signin">Sign in</Link>
      </header>

      <section className="home-hero">
        <h1>AI-Powered Technical Interviews</h1>
        <p>Schedule, run, and evaluate candidates with a live AI interview panel — from job description to scored report.</p>
        <Link to="/login" className="btn-hero-cta">Sign in with Google</Link>
      </section>

      <section className="home-steps">
        {STEPS.map(step => (
          <div className="home-step" key={step.title}>
            <div className="home-step-icon">{step.icon}</div>
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </div>
        ))}
      </section>

      <section className="home-features">
        {FEATURES.map(feature => (
          <div className="home-feature-card" key={feature.title}>
            <div className="home-feature-icon">{feature.icon}</div>
            <h4>{feature.title}</h4>
            <p>{feature.text}</p>
          </div>
        ))}
      </section>

      <footer className="home-footer">
        <p>Interview Prep — AI-driven technical assessments.</p>
      </footer>
    </div>
  );
}
