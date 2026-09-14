import { createContext, useContext, useEffect, useState } from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { getGuestToken, setGuestToken as persistGuestToken, clearGuestToken } from '../lib/guestSession'

type AuthContextType = {
  session: Session | null
  user: User | null
  isLoading: boolean
  signOut: () => Promise<void>
  getAccessToken: () => Promise<string | null>
  updateDisplayName: (name: string) => Promise<void>
  // Phase 6, Sub-phase 6D — Flow B (public link) guest identity. Deliberately
  // separate from `user`/`session`, which stay Supabase-only: a guest is
  // NOT treated as authenticated by the general ProtectedRoute (see
  // GuestOrAuthRoute for the one route — /interviews/:id — that accepts
  // either). This is a UX-scoping choice, not a security boundary — the
  // backend's own get_current_candidate_profile_id already honors a guest
  // token for every current_user_dependency-gated endpoint regardless of
  // frontend routing (see docs/CURRENT_DECISIONS.md's unresolved list).
  guestToken: string | null
  setGuestSession: (token: string, sessionId: string) => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [guestToken, setGuestTokenState] = useState<string | null>(() => getGuestToken())

  const setGuestSession = (token: string, sessionId: string) => {
    persistGuestToken(token, sessionId)
    setGuestTokenState(token)
  }

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setUser(session?.user ?? null)
      setIsLoading(false)
    })

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
      setUser(session?.user ?? null)
      setIsLoading(false)
    })

    return () => subscription.unsubscribe()
  }, [])

  const signOut = async () => {
    await supabase.auth.signOut()
    clearGuestToken()
    setGuestTokenState(null)
  }

  const getAccessToken = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    return session?.access_token || guestToken || null
  }

  const updateDisplayName = async (name: string) => {
    const trimmedName = name.trim()
    if (!trimmedName) throw new Error('Name cannot be empty')
    const { data, error } = await supabase.auth.updateUser({ data: { full_name: trimmedName, name: trimmedName } })
    if (error) throw error
    setUser(data.user)
    setSession((current) => current ? { ...current, user: data.user } : current)
  }

  return (
    <AuthContext.Provider value={{ session, user, isLoading, signOut, getAccessToken, updateDisplayName, guestToken, setGuestSession }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
