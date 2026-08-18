import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ArrowLeft, ArrowRight, AlertCircle } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'
import { AppShell } from '../components/layout/AppShell'
import { Button } from '../components/ui/Button'
import { Divider } from '../components/ui/Divider'

const LEVELS = [
  { value: 'junior', label: 'Junior' },
  { value: 'mid', label: 'Mid-Level' },
  { value: 'senior', label: 'Senior' },
] as const

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'ar', label: 'Arabic' },
] as const

export default function NewInterview() {
  const { getAccessToken } = useAuth()
  const navigate = useNavigate()

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [profileLoading, setProfileLoading] = useState(true)

  const [formData, setFormData] = useState({
    role: 'Backend Engineer',
    level: 'mid',
    language: 'en',
    duration: 25,
    thinking_time: 60,
    job_description: '',
  })

  // Pre-populate level from profile if available
  useEffect(() => {
    async function fetchProfile() {
      const token = await getAccessToken()
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/profiles/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          const inferredRole = data.professional_title || data.role
          if (data.confirmed_level) {
            setFormData((prev) => ({ ...prev, level: data.confirmed_level, role: inferredRole || prev.role }))
          } else if (data.recommended_level) {
            setFormData((prev) => ({
              ...prev,
              level: data.recommended_level,
              role: inferredRole || prev.role,
            }))
          } else if (inferredRole) {
            setFormData((prev) => ({ ...prev, role: inferredRole }))
          }
        }
      } catch (err) {
        console.error('Failed to fetch profile', err)
      } finally {
        setProfileLoading(false)
      }
    }
    fetchProfile()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      const token = await getAccessToken()
      const res = await fetch(`${API_BASE_URL}/api/v1/interviews/`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ configuration: formData }),
      })

      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || 'Failed to create session')
      }

      const session = await res.json()
      // Navigate to the interview session (preflight will be added in Phase 2B.3)
      navigate(`/interviews/${session.id}`)
    } catch (err: any) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const update = (field: string, value: string | number) =>
    setFormData((prev) => ({ ...prev, [field]: value }))

  if (profileLoading) {
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
      <div className="max-w-2xl space-y-12">
        {/* ── Back Link ─────────────────────────────────── */}
        <Link
          to="/dashboard"
          className="inline-flex items-center text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Back
        </Link>

        {/* ── Header ────────────────────────────────────── */}
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            New Interview
          </h1>
          <p className="text-muted-foreground text-lg">
            Configure your interview before entering.
          </p>
        </div>

        {/* ── Error ─────────────────────────────────────── */}
        {error && (
          <div className="flex items-start gap-3 p-4 rounded-md bg-destructive/10 border border-destructive/20 text-destructive text-sm">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* ── Configuration Form ────────────────────────── */}
        <form onSubmit={handleSubmit} className="space-y-10">
          {/* Role */}
          <fieldset className="space-y-2">
            <label
              htmlFor="role"
              className="text-xs font-medium uppercase tracking-widest text-muted-foreground"
            >
              Target Role
            </label>
            <input
              id="role"
              type="text"
              value={formData.role}
              onChange={(e) => update('role', e.target.value)}
              className="block w-full bg-transparent border-b border-border py-2 text-lg font-medium text-foreground focus:outline-none focus:border-primary transition-colors placeholder:text-muted-foreground/50"
              placeholder="e.g. Backend Engineer"
            />
          </fieldset>

          {/* Level + Language row */}
          <div className="grid sm:grid-cols-2 gap-x-12 gap-y-10">
            <fieldset className="space-y-2">
              <label
                htmlFor="level"
                className="text-xs font-medium uppercase tracking-widest text-muted-foreground"
              >
                Level
              </label>
              <select
                id="level"
                value={formData.level}
                onChange={(e) => update('level', e.target.value)}
                className="block w-full bg-transparent border-b border-border py-2 text-lg font-medium text-foreground focus:outline-none focus:border-primary transition-colors appearance-none cursor-pointer"
              >
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </fieldset>

            <fieldset className="space-y-2">
              <label
                htmlFor="language"
                className="text-xs font-medium uppercase tracking-widest text-muted-foreground"
              >
                Interview Language
              </label>
              <select
                id="language"
                value={formData.language}
                onChange={(e) => update('language', e.target.value)}
                className="block w-full bg-transparent border-b border-border py-2 text-lg font-medium text-foreground focus:outline-none focus:border-primary transition-colors appearance-none cursor-pointer"
              >
                {LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </fieldset>
          </div>

          <fieldset className="space-y-2">
            <label htmlFor="job_description" className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Specific Job Description
            </label>
            <textarea
              id="job_description"
              value={formData.job_description}
              onChange={(e) => update('job_description', e.target.value)}
              maxLength={12000}
              rows={5}
              placeholder="Paste the role expectations, core responsibilities, and required technologies."
              className="block w-full resize-y rounded-md border border-border bg-transparent px-3 py-2 text-sm leading-6 text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary"
            />
            <p className="text-xs text-muted-foreground">Used to tailor the interview without replacing questions grounded in your profile.</p>
          </fieldset>

          {/* Duration (read-only for now) */}
          <fieldset className="space-y-2">
            <label className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              Estimated Duration
            </label>
            <p className="text-lg font-medium text-foreground">
              {formData.duration} minutes
            </p>
          </fieldset>

          <Divider />

          {/* Submit */}
          <div className="flex justify-end">
            <Button
              type="submit"
              size="lg"
              className="px-10 text-base"
              disabled={submitting || !formData.role.trim()}
            >
              {submitting ? 'Creating…' : 'Continue'}
              {!submitting && <ArrowRight className="ml-2 h-4 w-4" />}
            </Button>
          </div>
        </form>
      </div>
    </AppShell>
  )
}
