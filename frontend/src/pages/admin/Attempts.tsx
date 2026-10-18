import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Card, CategoryBars, ErrorBox, ScoreRing, Spinner } from '../../components/ui'
import { categoryLabel, formatDate, formatDuration } from '../../format'
import { useAsync } from '../../hooks'
import type { AttemptMode } from '../../types'
import { adminApi } from './adminApi'
import { AttemptsTable, ModeLabel, Pager, RiskBadge } from './shared'

const PAGE = 25

export function AttemptsList() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState<AttemptMode | ''>((params.get('mode') as AttemptMode) ?? '')
  const [status, setStatus] = useState(params.get('status') ?? '')
  const [flaggedOnly, setFlaggedOnly] = useState(params.get('risk') === 'high')
  const [offset, setOffset] = useState(0)
  const { data, error, loading, reload } = useAsync(
    () => adminApi.attempts({ mode, status, risk: flaggedOnly ? 'high' : '', limit: PAGE, offset }),
    [mode, status, flaggedOnly, offset],
  )

  return (
    <Card>
      <div className="admin-toolbar">
        <div className="field">
          <label htmlFor="f-mode">Type</label>
          <select id="f-mode" value={mode} onChange={(e) => { setMode(e.target.value as AttemptMode | ''); setOffset(0) }}>
            <option value="">All</option>
            <option value="practice">Practice</option>
            <option value="certification">Certification</option>
            <option value="invite">Company invites</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="f-status">Status</label>
          <select id="f-status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0) }}>
            <option value="">All</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
          </select>
        </div>
        <label className="check check-inline">
          <input type="checkbox" checked={flaggedOnly} onChange={(e) => { setFlaggedOnly(e.target.checked); setOffset(0) }} />
          <span>Flagged only</span>
        </label>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? <Spinner /> : data ? (
        <>
          <AttemptsTable rows={data.attempts} />
          <Pager total={data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      ) : null}
    </Card>
  )
}

export function AttemptDetail() {
  const { attemptId = '' } = useParams()
  const { data, error, loading, reload } = useAsync(() => adminApi.attempt(attemptId), [attemptId])
  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const { attempt, review, integrity } = data

  return (
    <div className="stack">
      <Link to="/admin/attempts" className="back">
        ← Attempts
      </Link>
      <Card className="result-hero">
        <div className="result-hero-main">
          <ScoreRing percent={attempt.status === 'completed' ? attempt.percent : null} />
          <div>
            <p className="eyebrow">{formatDate(attempt.started_at)}</p>
            <h2>{attempt.test_title}</h2>
            <p className="muted">
              <Link to={`/admin/users/${attempt.user.id}`}>{attempt.user.name}</Link> · {attempt.user.email} ·{' '}
              <ModeLabel mode={attempt.mode} company={attempt.company} />
            </p>
            <p className="muted small">
              {attempt.status === 'completed'
                ? `${attempt.score} / ${attempt.max_score} points${review?.duration_seconds != null ? ` · ${formatDuration(review.duration_seconds)} used` : ''}${attempt.timed_out ? ' · ran out of time' : ''}`
                : `In progress: question ${data.progress.position + 1} of ${data.progress.total}`}
            </p>
          </div>
        </div>
      </Card>

      {integrity && (
        <Card title="Integrity" actions={<RiskBadge risk={integrity.risk} />}>
          {integrity.reasons.length > 0 && (
            <ul className="reasons">
              {integrity.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          <p className="muted small">
            Time outside the test window: {integrity.seconds_away} s. Events recorded: {data.events.length}.
          </p>
          {data.events.length > 0 && (
            <ol className="timeline">
              {data.events.map((e, i) => (
                <li key={i}>
                  <span className="tabular muted small">{new Date(e.occurred_at).toLocaleTimeString()}</span>
                  <span>
                    {e.label}
                    {e.duration_ms ? ` for ${Math.round(e.duration_ms / 1000)} s` : ''}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}

      {review && (
        <div className="results-grid">
          <Card title="Score by skill">
            <CategoryBars rows={review.categories} />
            {review.certificate && (
              <p className="small">
                Certificate <span className="tabular">{review.certificate.code}</span>: {review.certificate.status.replace('_', ' ')}.{' '}
                <Link to="/admin/certificates">Review queue</Link>
              </p>
            )}
          </Card>
          <Card title="Answers">
            <ol className="answer-list">
              {review.items.map((item) => (
                <li key={item.position} className={item.is_correct ? 'ok' : item.points ? 'part' : 'bad'}>
                  <div className="answer-head">
                    <span>
                      Q{item.position + 1} · {categoryLabel(item.question.category)} · {item.question.topic}
                    </span>
                    <span className="tabular">
                      {item.points ?? '-'}/{item.max_points}
                    </span>
                  </div>
                  {item.answer && typeof item.answer === 'object' && 'text' in item.answer && (
                    <blockquote className="answer-quote small">{item.answer.text}</blockquote>
                  )}
                  {item.answer && typeof item.answer === 'object' && 'code' in item.answer && (
                    <pre className="small">{item.answer.code}</pre>
                  )}
                  {item.grading?.feedback && <p className="small muted">{item.grading.feedback}</p>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      )}
    </div>
  )
}
