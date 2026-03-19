/**
 * API service - All backend API calls
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

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
      headers: {
        'Content-Type': 'application/json',
      },
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
      headers: {
        'Content-Type': 'application/json',
      },
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
      headers: {
        'Content-Type': 'application/json',
      },
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
      headers: {
        'Content-Type': 'application/json',
      },
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
      headers: {
        'Content-Type': 'application/json',
      },
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
      headers: {
        'Content-Type': 'application/json',
      },
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
