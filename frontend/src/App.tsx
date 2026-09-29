import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { RoleProvider } from './context/RoleContext'
import { ErrorBoundary } from './components/ErrorBoundary'
import AuthPage from './pages/Auth'
import InterviewSession from './pages/InterviewSession'

import InvitePage from './pages/InvitePage'
import ApplyPage from './pages/ApplyPage'
import VerbalPreview from './routes/dev/VerbalPreview'
import SectionsPreview from './routes/dev/SectionsPreview'
import StartPreview from './routes/dev/StartPreview'
import AdminPreview from './routes/dev/AdminPreview'
import ResultsPreview from './routes/dev/ResultsPreview'
import CandidateResultPreview from './routes/dev/CandidateResultPreview'
import JobCreatePreview from './routes/dev/JobCreatePreview'
import WorkspacePreview from './routes/dev/WorkspacePreview'
import AdminLayout from './routes/admin/AdminLayout'
import JobsListPage from './routes/admin/JobsListPage'
import JobCreatePage from './routes/admin/JobCreatePage'
import JobDetailPage from './routes/admin/JobDetailPage'
import JobResultsPage from './routes/admin/JobResultsPage'
import CandidateResultPage from './routes/admin/CandidateResultPage'

// DEV-only: a component that throws, to exercise the ErrorBoundary (see /dev/boom).
function DevBoom(): never {
  throw new Error("DevBoom: deliberate render error for the ErrorBoundary harness")
}

// Protected Route Component
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { user, isLoading } = useAuth()

  if (isLoading) return <div className="flex min-h-dvh items-center justify-center">Loading...</div>
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

  if (isLoading) return <div className="flex min-h-dvh items-center justify-center">Loading...</div>
  if (!user && !guestToken) return <Navigate to="/login" replace />

  return <>{children}</>
}

function App() {
  return (
    <AuthProvider>
      <RoleProvider>
        <BrowserRouter>
          {/* dvh, not vh: this wraps every route, so a `100vh` here kept the
              root taller than the visible viewport on mobile no matter what
              the page inside used -- which quietly undercut the dvh work in
              R4. Recorded in the plan's §7 during R4 and fixed here, before
              R5, which is entirely full-height layout. */}
          <div className="min-h-dvh bg-background text-foreground">
            {/* H2-E: a render error anywhere shows a recoverable screen instead of a blank page. */}
            <ErrorBoundary>
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
              {/* The live workspace gets its own boundary with candidate-facing copy (progress is checkpointed server-side). */}
              <Route path="/interviews/:id" element={<GuestOrAuthRoute><ErrorBoundary variant="interview"><InterviewSession /></ErrorBoundary></GuestOrAuthRoute>} />
              
              {/* DEV-only visual harness for the verbal stage (routes/dev/VerbalPreview.tsx). */}
              {import.meta.env.DEV && <Route path="/dev/verbal-preview" element={<VerbalPreview />} />}
              {import.meta.env.DEV && <Route path="/dev/sections-preview" element={<SectionsPreview />} />}
              {import.meta.env.DEV && <Route path="/dev/start-preview" element={<StartPreview />} />}
              {/* Responsive plan R0 (docs/responsive-design-plan.md): real admin shell / real workspace chrome without a backend. */}
              {import.meta.env.DEV && <Route path="/dev/admin-preview" element={<AdminPreview />} />}
              {/* R3-A: the results page against fixtures, so the harness can reach it without a login. */}
              {import.meta.env.DEV && <Route path="/dev/results-preview" element={<ResultsPreview />} />}
              {/* R2-C: the real JobCreatePage; it fetches nothing on mount. */}
              {import.meta.env.DEV && <Route path="/dev/job-create-preview" element={<JobCreatePreview />} />}
              {/* R3-B: the real CandidateResultPage over a stubbed GET. The
                  params are in the path because the page reads them from
                  useParams and will not fetch without a sessionId. */}
              {import.meta.env.DEV && <Route path="/dev/candidate-result-preview/:jobId/:sessionId" element={<CandidateResultPreview />} />}
              {import.meta.env.DEV && <Route path="/dev/candidate-result-preview" element={<Navigate to="/dev/candidate-result-preview/job-preview/sess-preview" replace />} />}
              {import.meta.env.DEV && <Route path="/dev/workspace-preview" element={<WorkspacePreview />} />}
              {/* H2-E: throws on render so the ErrorBoundary can be seen (DEV only, tree-shaken from prod). */}
              {import.meta.env.DEV && <Route path="/dev/boom" element={<DevBoom />} />}

              {/* Catch all */}
              <Route path="*" element={<Navigate to="/admin" replace />} />
            </Routes>
            </ErrorBoundary>
          </div>
        </BrowserRouter>
      </RoleProvider>
    </AuthProvider>
  )
}

export default App
