import React, { useState, useEffect } from 'react';
import { getQuestionsByRole, addQuestion } from '../services/api';

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
      // Convert tags comma separated to array or just leave as string
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
    <div className="container" style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Question Bank Management</h1>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          style={{ padding: '10px 15px', background: showAddForm ? '#6c757d' : '#28a745', color: '#FFF', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
        >
          {showAddForm ? 'Cancel' : '+ Add New Question'}
        </button>
      </div>

      {error && <div style={{ color: 'red', padding: '10px', border: '1px solid red', marginBottom: '20px' }}>{error}</div>}

      {/* Add Form */}
      {showAddForm && (
        <div style={{ backgroundColor: '#f9f9f9', padding: '20px', borderRadius: '8px', marginBottom: '20px' }}>
          <h2>Add New Question</h2>
          <form onSubmit={handleAddSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <div style={{ display: 'flex', gap: '15px' }}>
              <input name="role" placeholder="Role (e.g., software_engineer)" value={formData.role} onChange={handleInputChange} required style={{ flex: 1 }} />
              <input name="topic" placeholder="Topic (e.g., JavaScript)" value={formData.topic} onChange={handleInputChange} required style={{ flex: 1 }} />
              <select name="difficulty" value={formData.difficulty} onChange={handleInputChange} style={{ padding: '8px', flex: 1 }}>
                <option value="EASY">EASY</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="HARD">HARD</option>
              </select>
            </div>
            <textarea name="question_text" placeholder="Question Text" value={formData.question_text} onChange={handleInputChange} required rows={3} />
            <textarea name="ideal_answer" placeholder="Ideal Answer" value={formData.ideal_answer} onChange={handleInputChange} rows={3} />
            <input name="tags" placeholder="Tags (comma separated)" value={formData.tags} onChange={handleInputChange} />

            <button type="submit" disabled={isSubmitting} style={{ padding: '10px', background: '#007BFF', color: '#FFF', border: 'none', borderRadius: '4px', cursor: 'pointer', width: '200px' }}>
              {isSubmitting ? 'Saving...' : 'Save Question'}
            </button>
          </form>
        </div>
      )}

      {/* Filter and List */}
      <div style={{ marginBottom: '20px' }}>
        <label style={{ marginRight: '10px', fontWeight: 'bold' }}>Filter by Role:</label>
        <input
          type="text"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          placeholder="e.g., software_engineer"
          style={{ padding: '8px', width: '300px' }}
        />
      </div>

      {loading ? (
        <p>Loading questions for {roleFilter}...</p>
      ) : questions.length === 0 ? (
        <p>No questions found for this role. Try adding some or importing a JSON bank.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {questions.map(q => (
            <div key={q.id} style={{ padding: '15px', border: '1px solid #CCC', borderRadius: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                <strong>{q.topic} - {q.difficulty}</strong>
                <span style={{ fontSize: '0.8em', color: '#666' }}>Tags: {q.tags}</span>
              </div>
              <p style={{ margin: '0 0 10px 0', fontSize: '1.1em' }}>{q.question_text}</p>
              {q.ideal_answer && (
                <div style={{ backgroundColor: '#f1f8ff', padding: '10px', borderRadius: '4px', fontSize: '0.9em' }}>
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
