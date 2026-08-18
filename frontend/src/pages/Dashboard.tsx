import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ArrowRight, Plus } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'
import { AppShell } from '../components/layout/AppShell'
import { Button } from '../components/ui/Button'
import { Divider } from '../components/ui/Divider'

interface SessionSummary {
  id: string
  role: string
  level: string
  language: string
  status: string
  created_at: string
  started_at?: string
  completed_at?: string
  configuration?: {
    role: string
    level: string
    language: string
    duration: number
    thinking_time: number
  }
}

function formatLevel(level: string): string {
  const map: Record<string, string> = {
    junior: 'Junior',
    mid: 'Mid-Level',
    senior: 'Senior',
  }
  return map[level] || level
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatStatus(status: string): string {
  const map: Record<string, string> = {
    CREATED: 'Not started',
    IN_PROGRESS: 'In progress',
    COMPLETED: 'Completed',
    TERMINATED: 'Terminated',
    FAILED: 'Failed',
  }
  return map[status] || status
}

export default function Dashboard() {
  const { user, getAccessToken } = useAuth()
  const [profile, setProfile] = useState<any>(null)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      const token = await getAccessToken()
      if (!token) return

      try {
        const [profileRes, sessionsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/profiles/me`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${API_BASE_URL}/api/v1/interviews/`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ])

        if (profileRes.ok) setProfile(await profileRes.json())
        if (sessionsRes.ok) setSessions(await sessionsRes.json())
      } catch (err) {
        console.error('Failed to fetch dashboard data', err)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  // Separate sessions by status
  const activeSession = sessions.find(
    (s) => s.status === 'CREATED' || s.status === 'IN_PROGRESS'
  )
  const completedSessions = sessions.filter(
    (s) => s.status === 'COMPLETED' || s.status === 'TERMINATED'
  )

  const firstName =
    profile?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || ''

  if (loading) {
    return (
      <AppShell>
        <div className="flex justify-center py-20 text-muted-foreground">
          Loading…
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="max-w-3xl space-y-16">
        {/* ── Greeting ─────────────────────────────────── */}
        <section className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Good morning, {firstName}.
          </h1>
        </section>

        {/* ── Active / Resume Session ──────────────────── */}
        {activeSession && (
          <section className="space-y-4">
            <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Continue Interview
            </h2>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
              <div className="space-y-1">
                <p className="text-xl font-medium text-foreground">
                  {activeSession.role}
                </p>
                <p className="text-sm text-muted-foreground">
                  Technical Interview · {formatLevel(activeSession.level)}
                  {activeSession.configuration?.duration &&
                    ` · ${activeSession.configuration.duration} min`}
                </p>
              </div>

              <Link to={`/interviews/${activeSession.id}`}>
                <Button size="lg">
                  Continue <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </section>
        )}

        {/* ── New Interview CTA ────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
            {activeSession ? 'Or start fresh' : 'Your next interview'}
          </h2>

          <Link to="/interviews/new">
            <Button variant={activeSession ? 'outline' : 'primary'} size="lg">
              <Plus className="mr-2 h-4 w-4" /> New Interview
            </Button>
          </Link>
        </section>

        {/* ── Past Assessments ─────────────────────────── */}
        {completedSessions.length > 0 && (
          <>
            <Divider />

            <section className="space-y-6">
              <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                Past Assessments
              </h2>

              <div className="space-y-0">
                {completedSessions.map((session) => (
                  <Link
                    key={session.id}
                    to={`/interviews/${session.id}/result`}
                    className="flex items-center justify-between py-4 border-b border-border last:border-0 group transition-colors hover:bg-muted/30 -mx-2 px-2 rounded-sm"
                  >
                    <div className="space-y-0.5">
                      <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                        {session.role}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatLevel(session.level)} ·{' '}
                        {formatDate(session.created_at)}
                      </p>
                    </div>

                    <span className="text-xs text-muted-foreground">
                      {formatStatus(session.status)}
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </AppShell>
  )
}
