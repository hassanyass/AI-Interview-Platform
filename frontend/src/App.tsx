import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import AuthPage from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import NewInterview from './pages/NewInterview'
import InterviewSession from './pages/InterviewSession'
import FinalResult from './features/results/FinalResult'

// Protected Route Component
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isLoading } = useAuth()
  
  if (isLoading) return <div className="flex h-screen items-center justify-center">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  
  return <>{children}</>
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-background text-foreground">
          <Routes>
            {/* Public Route */}
            <Route path="/login" element={<AuthPage />} />
            
            {/* Protected Routes */}
            <Route path="/" element={<ProtectedRoute><Navigate to="/dashboard" replace /></ProtectedRoute>} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
            <Route path="/interviews/new" element={<ProtectedRoute><NewInterview /></ProtectedRoute>} />
            <Route path="/interviews/:id" element={<ProtectedRoute><InterviewSession /></ProtectedRoute>} />
            <Route path="/interviews/:id/result" element={<ProtectedRoute><FinalResult /></ProtectedRoute>} />
            
            {/* Catch all */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
