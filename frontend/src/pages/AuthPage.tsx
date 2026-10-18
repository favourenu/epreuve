import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { safeNext, useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'
import { NewPasswordFields, newPasswordProblem } from '../components/PasswordFields'
import { ErrorBox } from '../components/ui'

export function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { login, signup } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const isSignup = mode === 'signup'

  const [name, setName] = useState('')
  // Prefilled when arriving from an invitation (passed in router state, never the URL).
  const prefill = (useLocation().state as { email?: string } | null)?.email
  const [email, setEmail] = useState<string>(prefill ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const problem = isSignup ? newPasswordProblem(password, confirm) : null
    if (problem) {
      setError(problem)
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
    <AuthShell
      title={isSignup ? 'Create your account' : 'Welcome back'}
      intro={isSignup ? 'Your scores, history and study plans are saved to your account.' : 'Log in to continue practising.'}
    >
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
            autoComplete={isSignup ? 'email' : 'username'}
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        {isSignup ? (
          <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        ) : (
          <div className="field">
            <div className="label-row">
              <label htmlFor="password">Password</label>
              {/* Pass the typed email in router state, never in the URL (it would end up in history and logs). */}
              <Link to="/forgot-password" state={{ email: email.trim() }} className="label-link">
                Forgot password?
              </Link>
            </div>
            <div className="password-row">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                maxLength={128}
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
          </div>
        )}

        {error && <ErrorBox message={error} />}

        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? (isSignup ? 'Creating account...' : 'Logging in...') : isSignup ? 'Create account' : 'Log in'}
        </button>
      </form>

      <p className="auth-switch">
        {isSignup ? 'Already have an account?' : 'New to Épreuve?'}{' '}
        <Link to={otherLink}>{isSignup ? 'Log in' : 'Create an account'}</Link>
      </p>
    </AuthShell>
  )
}
