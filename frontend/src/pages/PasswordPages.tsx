import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'
import { NewPasswordFields, newPasswordProblem } from '../components/PasswordFields'
import { EmptyState, ErrorBox, Spinner } from '../components/ui'

export function ForgotPassword() {
  const location = useLocation()
  const [email, setEmail] = useState<string>((location.state as { email?: string } | null)?.email ?? '')
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await api.forgotPassword(email.trim())
      setSentTo(email.trim())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (sentTo) {
    return (
      <AuthShell title="Check your email">
        <div className="notice" role="status">
          <p>
            If an account exists for <strong>{sentTo}</strong>, we've sent a link to reset your password. It expires
            in 60 minutes.
          </p>
          <p className="muted small">
            Nothing arrived after a few minutes? Check your spam folder, make sure the address is right, or try again.
          </p>
        </div>
        <div className="actions">
          <Link to="/login" className="btn btn-primary">
            Back to log in
          </Link>
          <button type="button" className="btn btn-ghost" onClick={() => setSentTo(null)}>
            Use a different email
          </button>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Reset your password" intro="Enter the email you signed up with, and we'll send you a reset link.">
      <form onSubmit={submit} className="form">
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {error && <ErrorBox message={error} />}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? 'Sending...' : 'Send reset link'}
        </button>
      </form>
      <p className="auth-switch">
        Remembered it? <Link to="/login">Log in</Link>
      </p>
    </AuthShell>
  )
}

/** Read the token from ?token=... once, then remove it from the address bar and history. */
function useResetToken(): string | null {
  const location = useLocation()
  const navigate = useNavigate()
  const tokenRef = useRef<string | null>(new URLSearchParams(location.search).get('token'))
  useEffect(() => {
    if (location.search) navigate(location.pathname, { replace: true })
  }, [location.pathname, location.search, navigate])
  return tokenRef.current
}

export function ResetPassword() {
  const token = useResetToken()
  const { completeReset } = useAuth()
  const navigate = useNavigate()
  const [status, setStatus] = useState<'checking' | 'ready' | 'invalid'>(token ? 'checking' : 'invalid')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!token) return
    api
      .checkResetToken(token)
      .then((r) => {
        setEmail(r.email)
        setStatus('ready')
      })
      .catch(() => setStatus('invalid'))
  }, [token])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    const problem = newPasswordProblem(password, confirm)
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    try {
      await completeReset(token!, password)
      navigate('/dashboard', { replace: true, state: { notice: 'Your password was changed. Other devices have been signed out.' } })
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  if (status === 'checking') {
    return (
      <AuthShell title="Reset your password">
        <Spinner label="Checking your link" />
      </AuthShell>
    )
  }

  if (status === 'invalid') {
    return (
      <AuthShell title="This link has expired">
        <EmptyState
          icon="⏱"
          title="Reset links work once and expire after 60 minutes"
          action={
            <Link to="/forgot-password" className="btn btn-primary">
              Send a new link
            </Link>
          }
        >
          If you requested more than one, only the newest link works.
        </EmptyState>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Choose a new password" intro="You'll be signed in, and signed out on every other device.">
      <form onSubmit={submit} className="form">
        {/* Lets password managers save the new password against the right account. */}
        <div className="field">
          <label htmlFor="account-email">Account</label>
          <input id="account-email" type="email" autoComplete="username" value={email} readOnly />
        </div>
        <NewPasswordFields
          label="New password"
          password={password}
          confirm={confirm}
          onPassword={setPassword}
          onConfirm={setConfirm}
        />
        {error && <ErrorBox message={error} />}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? 'Saving...' : 'Save new password'}
        </button>
      </form>
    </AuthShell>
  )
}
