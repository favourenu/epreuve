import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api'
import type { User } from './types'

interface AuthState {
  /** undefined while the session is being checked, null when logged out. */
  user: User | null | undefined
  /** True right after an explicit log out, so protected pages go to the start page
   * instead of asking to log back in to the page that was open. */
  loggedOut: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (name: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  /** Set a new password with a reset token; signs in on success. */
  completeReset: (token: string, password: string) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [loggedOut, setLoggedOut] = useState(false)

  useEffect(() => {
    // Treat any failure (logged out, or server unreachable) as logged out; the
    // login page then surfaces connection errors when the user tries again.
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
    // Any 401 from the API (expired or revoked session) signs the user out locally.
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  const signedIn = useCallback((u: User) => {
    setLoggedOut(false)
    setUser(u)
  }, [])
  const login = useCallback(
    async (email: string, password: string) => signedIn(await api.login(email, password)),
    [signedIn],
  )
  const signup = useCallback(
    async (name: string, email: string, password: string) => signedIn(await api.signup(name, email, password)),
    [signedIn],
  )
  const completeReset = useCallback(
    async (token: string, password: string) => signedIn(await api.resetPassword(token, password)),
    [signedIn],
  )
  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setLoggedOut(true)
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loggedOut, login, signup, logout, completeReset }),
    [user, loggedOut, login, signup, logout, completeReset],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

function SessionCheck() {
  return (
    <div className="session-check" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="visually-hidden">Checking your session</span>
    </div>
  )
}

/** Only render children for signed-in users; otherwise send them to log in and back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loggedOut } = useAuth()
  const location = useLocation()
  if (user === undefined) return <SessionCheck />
  if (user === null && loggedOut) return <Navigate to="/" replace />
  if (user === null) {
    const next = location.pathname + location.search
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  }
  return <>{children}</>
}

/** For pages only logged-out visitors should see (landing, log in, sign up). */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user === undefined) return <SessionCheck />
  if (user) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

/** A safe post-login destination: only same-site paths, never another origin. */
// eslint-disable-next-line react-refresh/only-export-components
export function safeNext(next: string | null): string {
  return next && next.startsWith('/') && !next.startsWith('//') ? next : '/dashboard'
}
