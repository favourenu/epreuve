import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { safeNext, useAuth } from '../auth'
import { ErrorBox } from '../components/ui'

const MIN_PASSWORD = 8

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { login, signup } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const isSignup = mode === 'signup'

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (isSignup && password.length < MIN_PASSWORD) {
      setError(`Your password needs at least ${MIN_PASSWORD} characters.`)
      return
    }
    setBusy(true)
    try {
      if (isSignup) await signup(name.trim(), email.trim(), password)
      else await login(email.trim(), password)
      navigate(next, { replace: true })
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const otherLink = `${isSignup ? '/login' : '/signup'}${params.get('next') ? `?next=${encodeURIComponent(next)}` : ''}`

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>{isSignup ? 'Create your account' : 'Welcome back'}</h1>
        <p className="muted">
          {isSignup
            ? 'Your scores, history and study plans are saved to your account.'
            : 'Log in to continue practising.'}
        </p>

        <form onSubmit={submit} className="form">
          {isSignup && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input
                id="name"
                name="name"
                autoComplete="name"
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-row">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                required
                minLength={isSignup ? MIN_PASSWORD : undefined}
                maxLength={128}
                aria-describedby={isSignup ? 'password-hint' : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowPassword((v) => !v)}
                aria-pressed={showPassword}
                aria-controls="password"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            {isSignup && (
              <p id="password-hint" className="hint">
                At least {MIN_PASSWORD} characters.
              </p>
            )}
          </div>

          {error && <ErrorBox message={error} />}

          <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
            {busy ? (isSignup ? 'Creating account...' : 'Logging in...') : isSignup ? 'Create account' : 'Log in'}
          </button>
        </form>

        <p className="auth-switch">
          {isSignup ? 'Already have an account?' : 'New to Épreuve?'}{' '}
          <Link to={otherLink}>{isSignup ? 'Log in' : 'Create an account'}</Link>
        </p>
      </div>
    </div>
  )
}
