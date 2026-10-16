import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { useAsync } from '../hooks'

export function TestIntro() {
  const { testId = '' } = useParams()
  const navigate = useNavigate()
  const { data: test, error, loading, reload } = useAsync(() => api.test(testId), [testId])
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!test) return null

  async function start() {
    setStarting(true)
    setStartError(null)
    try {
      const attempt = await api.start(testId)
      navigate(`/attempts/${attempt.id}`)
    } catch (e) {
      setStartError((e as Error).message)
      setStarting(false)
    }
  }

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

        {startError && <ErrorBox message={startError} />}
        <div className="actions">
          <button className="btn btn-primary btn-lg" onClick={start} disabled={starting}>
            {starting ? 'Starting...' : 'Start test'}
          </button>
          <span className="muted">The timer starts immediately.</span>
        </div>
      </Card>
    </div>
  )
}
