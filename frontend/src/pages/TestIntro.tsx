import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { RulesModal } from '../components/Proctoring'
import { Card, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { formatDate } from '../format'
import { useAsync } from '../hooks'

export function TestIntro() {
  const { testId = '' } = useParams()
  const navigate = useNavigate()
  const { data: test, error, loading, reload } = useAsync(() => api.test(testId), [testId])
  const [starting, setStarting] = useState<'practice' | 'certification' | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [showRules, setShowRules] = useState(false)

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!test) return null

  async function start(mode: 'practice' | 'certification') {
    setStarting(mode)
    setStartError(null)
    try {
      const attempt = await api.start(testId, mode, mode === 'certification')
      navigate(`/attempts/${attempt.id}`)
    } catch (e) {
      setStartError((e as Error).message)
      setStarting(null)
    }
  }

  const cert = test.certificate
  const cooldownUntil = test.certification_available_at

  return (
    <div className="narrow stack">
      <Link to="/dashboard" className="back">
        ← Dashboard
      </Link>
      <Card>
        <p className="eyebrow">{test.skill_area}</p>
        <h1>{test.title}</h1>
        <p className="muted">{test.description}</p>

        <div className="intro-facts">
          <div>
            <span className="stat-label">Time limit</span>
            <strong>{test.time_limit_minutes} minutes</strong>
          </div>
          <div>
            <span className="stat-label">Questions</span>
            <strong>{test.question_count}</strong>
          </div>
          <div>
            <span className="stat-label">Best score</span>
            <strong>{test.best_percent == null ? '-' : <ScoreBadge percent={test.best_percent} />}</strong>
          </div>
        </div>

        <h2 className="section-title">Before you start</h2>
        <ul className="instructions">
          {test.instructions.map((line) => (
            <li key={line}>{line}</li>
          ))}
          <li>Questions are drawn at random from the bank, so each attempt is different.</li>
        </ul>

        {startError && !showRules && <ErrorBox message={startError} />}

        <div className="mode-grid">
          <section className="mode-card" aria-labelledby="practice-title">
            <h2 id="practice-title">Practice</h2>
            <p className="muted">Take it as often as you like. You'll get a score, explanations and an AI study plan.</p>
            <button className="btn btn-lg" onClick={() => start('practice')} disabled={starting !== null}>
              {starting === 'practice' ? 'Starting...' : 'Start practice'}
            </button>
          </section>

          <section className="mode-card mode-card-cert" aria-labelledby="cert-title">
            <h2 id="cert-title">Certification</h2>
            <p className="muted">
              Proctored. Score {test.certification_pass_percent}% or more for a certificate, or{' '}
              {test.certification_distinction_percent}% for a distinction, with a public link employers can verify.
            </p>
            {cert && (
              <p className={`cert-held cert-${cert.status}`}>
                {cert.status === 'issued'
                  ? `You hold a ${cert.level === 'distinction' ? 'distinction' : 'pass'} certificate (${Math.round(cert.percent)}%).`
                  : 'Your certificate is being reviewed.'}{' '}
                <Link to="/certificates">View</Link>
              </p>
            )}
            {cooldownUntil ? (
              <p className="hint">
                Next certification attempt available {formatDate(cooldownUntil)}. You can take one every{' '}
                {test.certification_cooldown_days} days.
              </p>
            ) : null}
            <button
              className="btn btn-primary btn-lg"
              onClick={() => setShowRules(true)}
              disabled={starting !== null || !!cooldownUntil}
            >
              {cooldownUntil ? 'Not available yet' : 'Start certification'}
            </button>
          </section>
        </div>
        <p className="muted small">The timer starts as soon as you begin.</p>
      </Card>

      {showRules && (
        <RulesModal
          title={`${test.title} certification`}
          busy={starting === 'certification'}
          error={startError}
          onCancel={() => {
            setShowRules(false)
            setStartError(null)
          }}
          onAgree={() => start('certification')}
        />
      )}
    </div>
  )
}
