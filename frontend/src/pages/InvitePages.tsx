import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { AuthShell } from '../components/AuthShell'
import { RulesModal } from '../components/Proctoring'
import { EmptyState, ErrorBox, Spinner } from '../components/ui'
import { formatDate } from '../format'
import { useAsync } from '../hooks'

/** Public landing page for a company's invitation (/invite/:token). */
export function InvitePage() {
  const { token = '' } = useParams()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { data: invite, error, loading } = useAsync(() => api.invite(token), [token])
  const [showRules, setShowRules] = useState(false)
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  if (loading || user === undefined) {
    return (
      <AuthShell title="Your invitation">
        <Spinner />
      </AuthShell>
    )
  }
  if (error || !invite) {
    return (
      <AuthShell title="Invitation not found">
        <ErrorBox message={error ?? 'This invitation link is invalid.'} />
      </AuthShell>
    )
  }

  async function start() {
    setBusy(true)
    setStartError(null)
    try {
      const attempt = await api.startInvite(token)
      navigate(`/attempts/${attempt.id}`)
    } catch (e) {
      setStartError((e as Error).message)
      setBusy(false)
    }
  }

  const next = `/invite/${token}`
  const closed = invite.status === 'cancelled' || invite.status === 'expired' || invite.status === 'completed'
  const rightUser = user && user.email === invite.email

  return (
    <AuthShell title={`${invite.company} invited you to an assessment`}>
      <div className="invite-facts">
        <div>
          <span className="stat-label">Assessment</span>
          <strong>{invite.test_title}</strong>
        </div>
        <div>
          <span className="stat-label">Time</span>
          <strong>{invite.time_limit_minutes} minutes</strong>
        </div>
        <div>
          <span className="stat-label">Questions</span>
          <strong>{invite.question_count}</strong>
        </div>
      </div>
      {invite.message && (
        <blockquote className="invite-message">
          <strong>Message from {invite.company}</strong>
          <p>{invite.message}</p>
        </blockquote>
      )}

      {closed ? (
        <EmptyState
          icon={invite.status === 'completed' ? '✓' : '⏱'}
          title={
            invite.status === 'completed'
              ? 'Assessment submitted'
              : invite.status === 'cancelled'
                ? 'This invitation was withdrawn'
                : 'This invitation has expired'
          }
        >
          {invite.status === 'completed'
            ? `Your results have been sent to ${invite.company}.`
            : `Contact ${invite.company} if you think this is a mistake.`}
        </EmptyState>
      ) : !user ? (
        <>
          <p className="muted">
            Hi {invite.candidate_name.split(' ')[0]}. To take this proctored assessment, log in or create a free account
            with <strong>{invite.email}</strong>. Use a computer with one screen; it takes about{' '}
            {invite.time_limit_minutes} minutes in one sitting. The invitation expires {formatDate(invite.expires_at)}.
          </p>
          <div className="actions">
            <Link className="btn btn-primary btn-lg" to={`/signup?next=${encodeURIComponent(next)}`} state={{ email: invite.email }}>
              Create account
            </Link>
            <Link className="btn btn-lg" to={`/login?next=${encodeURIComponent(next)}`} state={{ email: invite.email }}>
              Log in
            </Link>
          </div>
        </>
      ) : !rightUser ? (
        <>
          <ErrorBox
            message={`This invitation was sent to ${invite.email}, but you're logged in as ${user.email}.`}
          />
          <div className="actions">
            <button className="btn btn-primary" onClick={() => logout().then(() => navigate(`/login?next=${encodeURIComponent(next)}`, { state: { email: invite.email } }))}>
              Log out and switch account
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="muted">
            {invite.status === 'in_progress'
              ? 'You started this assessment already. The timer has kept running; resume to continue.'
              : `Your results go to ${invite.company}. You'll have one attempt, and the timer starts as soon as you begin.`}
          </p>
          {startError && !showRules && <ErrorBox message={startError} />}
          <div className="actions">
            {invite.status === 'in_progress' ? (
              <button className="btn btn-primary btn-lg" onClick={start} disabled={busy}>
                {busy ? 'Resuming...' : 'Resume assessment'}
              </button>
            ) : (
              <button className="btn btn-primary btn-lg" onClick={() => setShowRules(true)}>
                Begin assessment
              </button>
            )}
          </div>
        </>
      )}

      {showRules && (
        <RulesModal
          title={`${invite.test_title} for ${invite.company}`}
          busy={busy}
          error={startError}
          onCancel={() => setShowRules(false)}
          onAgree={start}
        />
      )}
    </AuthShell>
  )
}

/** Shown to an invited candidate after submitting: no score, just confirmation. */
export function SubmittedPage() {
  const { attemptId = '' } = useParams()
  const { data, error, loading } = useAsync(() => api.attempt(attemptId), [attemptId])
  if (loading) return <Spinner />
  return (
    <AuthShell title="Assessment submitted">
      {error ? (
        <ErrorBox message={error} />
      ) : (
        <EmptyState
          icon="✓"
          title={`Thank you. ${data?.company ? `Your results have been sent to ${data.company}.` : 'Your results have been sent.'}`}
          action={
            <Link to="/dashboard" className="btn btn-primary">
              Go to your dashboard
            </Link>
          }
        >
          {data?.test_title} is complete. While you're here, you can practise any assessment or earn a certificate.
        </EmptyState>
      )}
    </AuthShell>
  )
}
