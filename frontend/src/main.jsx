import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Home from './pages/Home'
import InterviewRoom from './pages/InterviewRoom'
import QuestionBank from './pages/QuestionBank'
import Report from './pages/Report'
import Login from './pages/Login'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Home />} />
          <Route path="/interview/:roomId" element={<InterviewRoom />} />
          <Route path="/questions" element={<ProtectedRoute><QuestionBank /></ProtectedRoute>} />
          <Route path="/report/:roomId" element={<Report />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)
