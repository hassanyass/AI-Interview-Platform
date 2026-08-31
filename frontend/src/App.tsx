import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { RoleProvider } from './context/RoleContext'
import AuthPage from './pages/Auth'
import InterviewSession from './pages/InterviewSession'

import InvitePage from './pages/InvitePage'
import ApplyPage from './pages/ApplyPage'
import AdminLayout from './routes/admin/AdminLayout'
import JobsListPage from './routes/admin/JobsListPage'
import JobCreatePage from './routes/admin/JobCreatePage'
import JobDetailPage from './routes/admin/JobDetailPage'
import JobResultsPage from './routes/admin/JobResultsPage'
import CandidateResultPage from './routes/admin/CandidateResultPage'

// Protected Route Component
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isLoading } = useAuth()

  if (isLoading) return <div className="flex h-screen items-center justify-center">Loading...</div>
  if (!user) return <Navigate to="/login" replace />

  return <>{children}</>
}

// Phase 6, Sub-phase 6D — accepts EITHER a real Supabase session OR a
// Flow B guest token. Deliberately scoped to only the routes a guest is
// meant to reach (/interviews/:id and its /result variant) rather than
// widening the general ProtectedRoute — see docs/CURRENT_DECISIONS.md's
// unresolved list: this is a UX-scoping choice, not a security boundary,
// since the backend already honors a guest token for any
// current_user_dependency-gated endpoint regardless of frontend routing.
const GuestOrAuthRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, guestToken, isLoading } = useAuth()

  if (isLoading) return <div className="flex h-screen items-center justify-center">Loading...</div>
  if (!user && !guestToken) return <Navigate to="/login" replace />

  return <>{children}</>
}

function App() {
  return (
    <AuthProvider>
      <RoleProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-background text-foreground">
            <Routes>
              {/* Public Routes */}
              <Route path="/login" element={<AuthPage />} />
              <Route path="/invite/:token" element={<InvitePage />} />
              <Route path="/apply/:token" element={<ApplyPage />} />

              {/* Admin Routes */}
              <Route path="/admin" element={<ProtectedRoute><AdminLayout /></ProtectedRoute>}>
                <Route index element={<Navigate to="jobs" replace />} />
                <Route path="dashboard" element={<Navigate to="jobs" replace />} />
                <Route path="jobs" element={<JobsListPage />} />
                <Route path="jobs/new" element={<JobCreatePage />} />
                <Route path="jobs/:id" element={<JobDetailPage />} />
                <Route path="jobs/:id/results" element={<JobResultsPage />} />
                <Route path="jobs/:jobId/results/:sessionId" element={<CandidateResultPage />} />
                <Route path="settings" element={<div>Settings Placeholder</div>} />
              </Route>

              {/* Protected Routes (Candidate Facing) */}
              <Route path="/" element={<Navigate to="/admin" replace />} />
              <Route path="/interviews/:id" element={<GuestOrAuthRoute><InterviewSession /></GuestOrAuthRoute>} />
              
              {/* Catch all */}
              <Route path="*" element={<Navigate to="/admin" replace />} />
            </Routes>
          </div>
        </BrowserRouter>
      </RoleProvider>
    </AuthProvider>
  )
}

export default App
