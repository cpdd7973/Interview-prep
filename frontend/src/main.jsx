import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import InterviewRoom from './pages/InterviewRoom'
import QuestionBank from './pages/QuestionBank'
import Report from './pages/Report'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/interview/:roomId" element={<InterviewRoom />} />
        <Route path="/questions" element={<QuestionBank />} />
        <Route path="/report/:roomId" element={<Report />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
