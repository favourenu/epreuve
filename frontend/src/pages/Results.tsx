import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { CodeEditor } from '../components/LazyCodeEditor'
import { Markdown } from '../components/Markdown'
import { Card, CategoryBars, DifficultyTag, EmptyState, ErrorBox, ScoreRing, Spinner } from '../components/ui'
import { categoryLabel, formatDate, formatDuration, formatValue } from '../format'
import { useAsync } from '../hooks'
import type { AttemptReview, ReviewItem } from '../types'

const POLL_MS = 3000

export function Results() {
  const { attemptId = '' } = useParams()
  const { data: review, error, loading, reload, setData } = useAsync(() => api.review(attemptId), [attemptId])
  const [retrying, setRetrying] = useState(false)
  const [filter, setFilter] = useState<'all' | 'wrong'>('all')
  const pending = review?.attempt.feedback_status === 'pending'

  // Poll while the AI report is being generated.
  useEffect(() => {
    if (!pending) return
    const id = window.setInterval(() => {
      api.review(attemptId).then(setData).catch(() => {})
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [pending, attemptId, setData])

  if (loading && !review) return <Spinner label="Grading" />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!review) return null

  async function retry() {
    setRetrying(true)
    try {
      await api.retryFeedback(attemptId)
      setData(await api.review(attemptId))
    } finally {
      setRetrying(false)
    }
  }

  const { attempt } = review
  const items = filter === 'wrong' ? review.items.filter((i) => i.is_correct !== true) : review.items

  return (
    <div className="stack">
      <Link to="/dashboard" className="back">
        ← Dashboard
      </Link>

      <Card className="result-hero">
        <div className="result-hero-main">
          <ScoreRing percent={attempt.percent} />
          <div>
            <p className="eyebrow">{formatDate(attempt.started_at)}</p>
            <h1>{attempt.test_title}</h1>
            <p className="muted">
              {attempt.score} / {attempt.max_score} points
              {review.duration_seconds != null && ` · ${formatDuration(review.duration_seconds)} used`}
              {attempt.timed_out && <span className="badge badge-bad ml">Ran out of time</span>}
            </p>
            {pending && review.items.some((i) => i.points == null) && (
              <p className="muted small">Written answers are still being graded; the score may go up.</p>
            )}
          </div>
        </div>
        <div className="actions">
          <Link className="btn btn-primary" to={`/tests/${attempt.test_id}`}>
            Retake
          </Link>
        </div>
      </Card>

      <div className="results-grid">
        <Card title="Score by skill">
          <CategoryBars rows={review.categories} />
        </Card>
        <FeedbackCard review={review} onRetry={retry} retrying={retrying} />
      </div>

      <Card
        title="Question review"
        actions={
          <div className="segmented" role="group" aria-label="Filter questions">
            <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>
              All ({review.items.length})
            </button>
            <button className={filter === 'wrong' ? 'active' : ''} onClick={() => setFilter('wrong')}>
              Missed ({review.items.filter((i) => i.is_correct !== true).length})
            </button>
          </div>
        }
      >
        <div className="review-list">
          {items.map((item) => (
            <ReviewEntry key={item.position} item={item} />
          ))}
          {items.length === 0 && (
            <EmptyState icon="✓" title="Nothing missed">
              Every question earned full marks. Try a harder test, or the full assessment.
            </EmptyState>
          )}
        </div>
      </Card>
    </div>
  )
}

function FeedbackCard({ review, onRetry, retrying }: { review: AttemptReview; onRetry: () => void; retrying: boolean }) {
  const status = review.attempt.feedback_status
  const fb = review.feedback
  return (
    <Card
      title="AI coach report"
      actions={review.feedback_provider ? <span className="chip small">via {review.feedback_provider}</span> : undefined}
    >
      {status === 'pending' && <Spinner label="Analysing your attempt" />}
      {status === 'failed' && (
        <div className="stack-sm">
          <ErrorBox
            message={
              review.items.some((i) => i.points == null)
                ? "The AI report couldn't be generated, so written answers are not scored yet. Retry when an AI provider is available."
                : "The AI report couldn't be generated. Your score above is final; only the coaching report is missing."
            }
          />
          {review.feedback_error && <pre className="run-error small">{review.feedback_error}</pre>}
          <button className="btn" onClick={onRetry} disabled={retrying}>
            {retrying ? 'Retrying...' : 'Retry AI report'}
          </button>
        </div>
      )}
      {status === 'ready' && fb && (
        <div className="report">
          <p className="report-summary">{fb.summary}</p>
          {fb.strengths.length > 0 && (
            <>
              <h3>Strengths</h3>
              <ul>{fb.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
            </>
          )}
          {fb.weaknesses.length > 0 && (
            <>
              <h3>To improve</h3>
              <ul>{fb.weaknesses.map((s) => <li key={s}>{s}</li>)}</ul>
            </>
          )}
          {fb.study_plan.length > 0 && (
            <>
              <h3>Study plan</h3>
              <ol className="study-plan">
                {fb.study_plan.map((s) => (
                  <li key={s.topic}>
                    <div className="study-head">
                      <strong>{s.topic}</strong>
                      <span className={`tag tag-prio-${s.priority}`}>{s.priority}</span>
                    </div>
                    <p className="muted small">{s.why}</p>
                    <p className="small">{s.how_to_practice}</p>
                  </li>
                ))}
              </ol>
            </>
          )}
          {fb.test_taking_tips.length > 0 && (
            <>
              <h3>Test-taking tips</h3>
              <ul>{fb.test_taking_tips.map((s) => <li key={s}>{s}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </Card>
  )
}

function verdict(item: ReviewItem) {
  if (item.answer == null) return { label: 'Skipped', tone: 'none' }
  if (item.points == null) return { label: 'Awaiting grading', tone: 'none' }
  if (item.is_correct) return { label: 'Correct', tone: 'good' }
  if (item.points > 0) return { label: 'Partial credit', tone: 'ok' }
  return { label: 'Incorrect', tone: 'bad' }
}

function ReviewEntry({ item }: { item: ReviewItem }) {
  const [open, setOpen] = useState(item.is_correct !== true)
  const q = item.question
  const v = verdict(item)

  return (
    <article className={`review-item review-${v.tone}`}>
      <button className="review-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="review-num">Q{item.position + 1}</span>
        <span className="review-title">
          {categoryLabel(q.category)} · {q.topic}
        </span>
        <DifficultyTag level={q.difficulty} />
        <span className={`badge badge-${v.tone}`}>{v.label}</span>
        <span className="muted tabular small">
          {item.points ?? '-'}/{item.max_points}
          {item.time_spent_seconds != null && ` · ${formatDuration(item.time_spent_seconds)}`}
        </span>
      </button>

      {open && (
        <div className="review-body">
          <Markdown>{q.prompt}</Markdown>

          {q.type === 'mcq' && (
            <ul className="review-options">
              {q.options!.map((opt, i) => {
                const chosen = item.answer === i
                const correct = q.answer === i
                return (
                  <li key={i} className={correct ? 'opt-correct' : chosen ? 'opt-wrong' : ''}>
                    <span className="option-letter">{String.fromCharCode(65 + i)}</span>
                    <Markdown inline>{opt}</Markdown>
                    {correct && <span className="badge badge-good">Best answer</span>}
                    {chosen && !correct && <span className="badge badge-bad">Your answer</span>}
                    {chosen && correct && <span className="badge badge-good">Your answer</span>}
                    {q.option_scores && (
                      <span className="muted small">
                        {q.option_scores[i]} {q.option_scores[i] === 1 ? 'pt' : 'pts'}
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          {q.type === 'code' && <CodeReview item={item} />}

          {q.type === 'written' && (
            <div className="stack-sm">
              <h4>Your answer {item.grading?.word_count != null && <span className="muted small">({item.grading.word_count} words)</span>}</h4>
              <blockquote className="answer-quote">{typeof item.answer === 'object' && item.answer && 'text' in item.answer ? item.answer.text : '(no answer)'}</blockquote>
              {item.grading?.feedback && (
                <div className="feedback-box">
                  <strong>Assessor feedback</strong>
                  <p>{item.grading.feedback}</p>
                </div>
              )}
              {q.rubric && (
                <>
                  <h4>What graders look for</h4>
                  <ul>{q.rubric.map((r) => <li key={r}>{r}</li>)}</ul>
                </>
              )}
              {q.model_answer && (
                <details>
                  <summary>Example strong answer</summary>
                  <Markdown>{q.model_answer}</Markdown>
                </details>
              )}
            </div>
          )}

          {q.explanation && (
            <div className="explanation">
              <strong>Explanation</strong>
              <Markdown>{q.explanation}</Markdown>
            </div>
          )}
        </div>
      )}
    </article>
  )
}

function CodeReview({ item }: { item: ReviewItem }) {
  const g = item.grading
  const code = typeof item.answer === 'object' && item.answer && 'code' in item.answer ? item.answer.code : ''
  return (
    <div className="stack-sm">
      {g?.error && <pre className="run-error">{g.error}</pre>}
      {g?.tests && (
        <table className="test-table">
          <colgroup>
            <col style={{ width: '5.5rem' }} />
            <col />
            <col />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th />
              <th>Input</th>
              <th>Expected</th>
              <th>Your output</th>
            </tr>
          </thead>
          <tbody>
            {g.tests.map((t, i) => (
              <tr key={i}>
                <td className={t.passed ? 'pass' : 'fail'}>
                  {t.passed ? '✓' : '✗'}
                  {t.hidden && <span className="muted small"> hidden</span>}
                </td>
                <td><code>{Array.isArray(t.args) ? t.args.map((a) => formatValue(a)).join(', ') : formatValue(t.args)}</code></td>
                <td><code>{formatValue(t.expected)}</code></td>
                <td><code>{t.error ?? formatValue(t.output)}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {code && (
        <>
          <h4>Your code</h4>
          <CodeEditor value={code} readOnly height={Math.min(400, 22 * (code.split('\n').length + 2))} />
        </>
      )}
      {item.question.reference_solution && (
        <details>
          <summary>Reference solution</summary>
          <CodeEditor
            value={item.question.reference_solution}
            readOnly
            height={Math.min(400, 22 * (item.question.reference_solution.split('\n').length + 2))}
          />
        </details>
      )}
    </div>
  )
}
