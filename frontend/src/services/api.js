/**
 * API service - All backend API calls
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

/**
 * Get auth headers from localStorage token
 */
const getAuthHeaders = () => {
  const token = localStorage.getItem('auth_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

/**
 * Get room status with polling support
 */
export const getRoomStatus = async (roomId, signal = null) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/room/${roomId}/status`, {
      signal,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error;
    }
    console.error('Error fetching room status:', error);
    throw error;
  }
};

/**
 * Schedule a new interview
 */
export const scheduleInterview = async (interviewData) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/interviews/schedule`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(interviewData),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error scheduling interview:', error);
    throw error;
  }
};

/**
 * List all interviews with optional status filter
 */
export const listInterviews = async (status = null) => {
  try {
    const url = status 
      ? `${API_BASE_URL}/api/interviews?status=${status}`
      : `${API_BASE_URL}/api/interviews`;

    const response = await fetch(url, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error listing interviews:', error);
    throw error;
  }
};

/**
 * Cancel an interview
 */
export const cancelInterview = async (roomId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/interviews/${roomId}/cancel`, {
      method: 'POST',
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error cancelling interview:', error);
    throw error;
  }
};

/**
 * Get questions by role
 */
export const getQuestionsByRole = async (role) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/questions?role=${role}`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching questions:', error);
    throw error;
  }
};

/**
 * Add a new question
 */
export const addQuestion = async (questionData) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/questions`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(questionData),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error adding question:', error);
    throw error;
  }
};

/**
 * Get evaluation report
 */
export const getEvaluationReport = async (roomId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluations/${roomId}`, {
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching evaluation:', error);
    throw error;
  }
};

/**
 * Download the evaluation report PDF
 */
export const downloadEvaluationReportPdf = async (roomId) => {
  const response = await fetch(`${API_BASE_URL}/api/evaluations/${roomId}/pdf`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP error! status: ${response.status}`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${roomId}_report.pdf`;
  document.body.appendChild(a);
  a.click();

  // Defer cleanup — revoking the blob URL synchronously after click()
  // cancels the download in Chrome before it finishes writing the file.
  setTimeout(() => {
    a.remove();
    window.URL.revokeObjectURL(url);
  }, 1000);
};
