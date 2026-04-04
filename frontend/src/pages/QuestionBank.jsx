import React, { useState, useEffect } from 'react';
import { getQuestionsByRole, addQuestion } from '../services/api';
import './QuestionBank.css';

export default function QuestionBank() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [roleFilter, setRoleFilter] = useState('software_engineer');

  // Add question form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState({
    role: 'software_engineer',
    topic: '',
    difficulty: 'MEDIUM',
    question_text: '',
    ideal_answer: '',
    tags: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchQuestions = async () => {
    if (!roleFilter) return;
    setLoading(true);
    try {
      const data = await getQuestionsByRole(roleFilter);
      if (data.success) {
        setQuestions(data.questions || []);
      } else {
        setError(data.error || "Failed to load questions.");
      }
    } catch (err) {
      setError(err.message || "Network error while fetching questions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuestions();
  }, [roleFilter]);

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleAddSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const payload = { ...formData };
      const res = await addQuestion(payload);
      if (res.success) {
        setShowAddForm(false);
        setFormData({ ...formData, topic: '', question_text: '', ideal_answer: '', tags: '' });
        fetchQuestions();
      } else {
        setError(res.error || "Failed to add question.");
      }
    } catch (err) {
      setError(err.message || "Error adding question.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="qb-container">
      <div className="qb-header">
        <h1>Question Bank Management</h1>
        <button
          className={`btn-toggle-add ${showAddForm ? 'cancel' : ''}`}
          onClick={() => setShowAddForm(!showAddForm)}
        >
          {showAddForm ? 'Cancel' : '+ Add New Question'}
        </button>
      </div>

      {error && <div className="qb-error-msg">{error}</div>}

      {/* Add Form */}
      {showAddForm && (
        <div className="qb-add-form-card">
          <h2>Add New Question</h2>
          <form className="qb-form-grid" onSubmit={handleAddSubmit}>
            <div className="qb-form-row">
              <input className="qb-input" name="role" placeholder="Role (e.g., software_engineer)" value={formData.role} onChange={handleInputChange} required />
              <input className="qb-input" name="topic" placeholder="Topic (e.g., JavaScript)" value={formData.topic} onChange={handleInputChange} required />
              <select className="qb-select" name="difficulty" value={formData.difficulty} onChange={handleInputChange}>
                <option value="EASY">EASY</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HARD">HARD</option>
              </select>
            </div>
            
            <textarea className="qb-textarea" name="question_text" placeholder="Question Text" value={formData.question_text} onChange={handleInputChange} required rows={3} />
            <textarea className="qb-textarea" name="ideal_answer" placeholder="Ideal Answer" value={formData.ideal_answer} onChange={handleInputChange} rows={3} />
            <input className="qb-input" name="tags" placeholder="Tags (comma separated)" value={formData.tags} onChange={handleInputChange} />

            <button type="submit" className="qb-btn-submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : 'Save Question'}
            </button>
          </form>
        </div>
      )}

      {/* Filter and List */}
      <div className="qb-filter-section">
        <label>Filter by Role:</label>
        <input
          className="qb-input qb-filter-input"
          type="text"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          placeholder="e.g., software_engineer"
        />
      </div>

      {loading ? (
        <p>Loading questions for {roleFilter}...</p>
      ) : questions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b', background: '#f8fafc', borderRadius: '12px' }}>
          No questions found for this role. Try adding some or importing a JSON bank.
        </div>
      ) : (
        <div className="qb-list">
          {questions.map(q => (
            <div key={q.id} className="qb-card">
              <div className="qb-card-header">
                <div>
                  <div className="qb-card-title">{q.topic}</div>
                  <div className="qb-card-tags">
                    {q.tags ? q.tags.split(',').map(tag => <span key={tag} className="qb-tag">{tag.trim()}</span>) : null}
                  </div>
                </div>
                <span className={`qb-card-difficulty ${q.difficulty}`}>{q.difficulty}</span>
              </div>
              
              <div className="qb-question-text">{q.question_text}</div>
              
              {q.ideal_answer && (
                <div className="qb-ideal-answer">
                  <strong>Ideal Answer:</strong> <br />
                  {q.ideal_answer}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
