import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { safeNext, useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'
import { ErrorBox, Spinner } from '../components/ui'

const CODE_LENGTH = 6

function countdown(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

/** After signing up: enter the 6-digit code we emailed. Nothing else works until then. */
export function VerifyEmail() {
  const { user, confirmEmail, logout } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))

  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)
  const [sending, setSending] = useState(false)
  const submitted = useRef('')

  // How long until a new code may be sent (one was just sent on sign-up).
  useEffect(() => {
    if (!user || user.email_verified) return
    api.emailStatus().then((s) => setWait(s.resend_after_seconds), () => undefined)
  }, [user])

  useEffect(() => {
    if (wait <= 0) return
    const t = window.setTimeout(() => setWait((w) => w - 1), 1000)
    return () => window.clearTimeout(t)
  }, [wait])

  if (user === undefined) return <Spinner />
  if (user === null) return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
  if (user.email_verified) return <Navigate to={next} replace />

  async function confirm(value: string) {
    if (value.length !== CODE_LENGTH || busy) return
    submitted.current = value
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await confirmEmail(value) // the redirect above then takes over
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  function onChange(raw: string) {
    const digits = raw.replace(/\D/g, '').slice(0, CODE_LENGTH)
    setCode(digits)
    // Submit as soon as a full code is typed or pasted (but not the same wrong code twice).
    if (digits.length === CODE_LENGTH && digits !== submitted.current) void confirm(digits)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    void confirm(code)
  }

  async function resend() {
    setSending(true)
    setError(null)
    setNotice(null)
    try {
      const r = await api.resendCode()
      setNotice(`${r.detail} The previous code no longer works.`)
      setWait(r.resend_after_seconds)
      setCode('')
      submitted.current = ''
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSending(false)
    }
  }

  async function startOver() {
    await logout()
    navigate('/signup', { replace: true })
  }

  return (
    <AuthShell
      title="Confirm your email"
      intro={
        <>
          We sent a 6-digit code to <strong>{user.email}</strong>. Enter it to finish creating your account.
        </>
      }
    >
      <form onSubmit={submit} className="form">
        <div className="field">
          <label htmlFor="code">Confirmation code</label>
          <input
            id="code"
            name="code"
            className="code-input"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={CODE_LENGTH + 2}
            required
            autoFocus
            aria-invalid={!!error}
            aria-describedby="code-hint"
            value={code}
            onChange={(e) => onChange(e.target.value)}
          />
          <span id="code-hint" className="hint">
            The code expires in 15 minutes. Can't find it? Check your spam folder.
          </span>
        </div>
        {error && <ErrorBox message={error} />}
        {notice && (
          <p className="notice small" role="status">
            {notice}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy || code.length !== CODE_LENGTH}>
          {busy ? 'Confirming...' : 'Confirm email'}
        </button>
      </form>

      <div className="verify-actions">
        <button type="button" className="btn btn-ghost btn-sm" onClick={resend} disabled={sending || wait > 0}>
          {sending ? 'Sending...' : wait > 0 ? `Send a new code in ${countdown(wait)}` : 'Send a new code'}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={startOver}>
          Wrong email? Sign up again
        </button>
      </div>
    </AuthShell>
  )
}
