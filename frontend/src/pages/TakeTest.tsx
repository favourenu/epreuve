import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import { CodeEditor } from '../components/LazyCodeEditor'
import { Markdown } from '../components/Markdown'
import { DifficultyTag, ErrorBox, ProgressBar, Spinner } from '../components/ui'
import { categoryLabel, draftStore, formatDuration, formatValue, wordCount } from '../format'
import type { AttemptState, PublicQuestion, RunResult } from '../types'

type Draft = number | string | null

function draftKey(attemptId: string, position: number) {
  return `epreuve:draft:${attemptId}:${position}`
}

function initialDraft(attemptId: string, position: number, q: PublicQuestion): Draft {
  const saved = draftStore.get(draftKey(attemptId, position))
  if (q.type === 'mcq') return saved == null ? null : Number(saved)
  if (q.type === 'code') return saved ?? q.starter_code ?? ''
  return saved ?? ''
}

function toAnswer(q: PublicQuestion, draft: Draft): unknown {
  if (q.type === 'mcq') return draft
  if (q.type === 'code') return { code: draft as string }
  return { text: draft as string }
}

function hasAnswer(q: PublicQuestion, draft: Draft): boolean {
  if (q.type === 'mcq') return draft != null
  if (q.type === 'code') return typeof draft === 'string' && draft.trim() !== '' && draft !== q.starter_code
  return typeof draft === 'string' && draft.trim() !== ''
}

/** Remaining seconds from the server deadline, corrected for client clock skew. */
function useCountdown(attempt: AttemptState | null) {
  const skewRef = useRef(0)
  const [remaining, setRemaining] = useState<number | null>(null)

  useEffect(() => {
    if (!attempt) return
    skewRef.current = new Date(attempt.server_time).getTime() - Date.now()
    const deadline = new Date(attempt.deadline).getTime()
    const tick = () => setRemaining(Math.max(0, Math.round((deadline - (Date.now() + skewRef.current)) / 1000)))
    tick()
    const id = window.setInterval(tick, 500)
    return () => window.clearInterval(id)
  }, [attempt])

  return remaining
}

export function TakeTest() {
  const { attemptId = '' } = useParams()
  const navigate = useNavigate()
  const [attempt, setAttempt] = useState<AttemptState | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>(null)
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmFinish, setConfirmFinish] = useState(false)
  const [run, setRun] = useState<RunResult | null>(null)
  const [running, setRunning] = useState(false)
  const closingRef = useRef(false)
  const remaining = useCountdown(attempt)

  const goToResults = useCallback(() => navigate(`/attempts/${attemptId}/results`, { replace: true }), [attemptId, navigate])

  const applyState = useCallback(
    (state: AttemptState) => {
      if (state.status === 'completed') {
        goToResults()
        return
      }
      setAttempt(state)
      setRun(null)
      if (state.question) setDraft(initialDraft(state.id, state.position, state.question))
    },
    [goToResults],
  )

  const load = useCallback(() => {
    setLoadError(null)
    api.attempt(attemptId).then(applyState).catch((e: Error) => setLoadError(e.message))
  }, [attemptId, applyState])

  useEffect(load, [load])

  // Latest values for async handlers that outlive a render (e.g. the time-up effect).
  const latest = useRef({ attempt, draft })
  latest.current = { attempt, draft }

  /** Save the answer currently on screen, if any, so finishing or time-up doesn't discard it. */
  const saveCurrentDraft = useCallback(async () => {
    const { attempt: a, draft: d } = latest.current
    if (!a?.question || !hasAnswer(a.question, d)) return
    try {
      await api.answer(a.id, a.position, toAnswer(a.question, d))
      draftStore.remove(draftKey(a.id, a.position))
    } catch {
      /* past the deadline's grace period: the server has already closed the attempt */
    }
  }, [])

  // Time is up: save what's on screen (the server allows a few seconds' grace),
  // then ask the server, which closes the attempt and grades it.
  useEffect(() => {
    if (remaining === 0 && !closingRef.current) {
      closingRef.current = true
      saveCurrentDraft()
        .then(() => api.attempt(attemptId))
        .then(applyState)
        .catch(() => goToResults())
    }
  }, [remaining, attemptId, applyState, goToResults, saveCurrentDraft])

  // Warn before leaving mid-test. The timer keeps running on the server either way.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  useEffect(() => {
    if (!confirmFinish) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setConfirmFinish(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirmFinish])

  function updateDraft(value: Draft) {
    setDraft(value)
    if (attempt) {
      const key = draftKey(attempt.id, attempt.position)
      if (value == null) draftStore.remove(key)
      else draftStore.set(key, String(value))
    }
  }

  async function handleError(e: unknown) {
    if (e instanceof ApiError && e.status === 409) {
      // Time ran out or the state changed elsewhere (e.g. another tab); resync.
      const state = await api.attempt(attemptId).catch(() => null)
      if (state) applyState(state)
      if (state?.status !== 'completed') setActionError(e.message)
    } else {
      setActionError((e as Error).message)
    }
  }

  async function submit(skip: boolean) {
    if (!attempt?.question) return
    setSubmitting(true)
    setActionError(null)
    try {
      const answer = skip ? null : toAnswer(attempt.question, draft)
      const next = await api.answer(attempt.id, attempt.position, answer)
      draftStore.remove(draftKey(attempt.id, attempt.position))
      applyState(next)
      window.scrollTo({ top: 0 })
    } catch (e) {
      await handleError(e)
    } finally {
      setSubmitting(false)
    }
  }

  async function runCode() {
    if (!attempt?.question || typeof draft !== 'string') return
    setRunning(true)
    setActionError(null)
    try {
      setRun(await api.run(attempt.id, attempt.position, draft))
    } catch (e) {
      await handleError(e)
    } finally {
      setRunning(false)
    }
  }

  async function finishNow() {
    setSubmitting(true)
    try {
      await saveCurrentDraft()
      const state = await api.attempt(attemptId)
      if (state.status === 'in_progress') await api.finish(attemptId)
      goToResults()
    } catch (e) {
      await handleError(e)
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <div className="container narrow">
        <ErrorBox message={loadError} onRetry={load} />
      </div>
    )
  }
  if (!attempt || !attempt.question) return <div className="container"><Spinner /></div>

  const q = attempt.question
  const isLast = attempt.position === attempt.total_questions - 1
  const lowTime = remaining != null && remaining <= 60
  const answered = hasAnswer(q, draft)

  return (
    <div className="test-shell">
      <header className="test-bar">
        <div className="test-bar-title">
          <strong>{attempt.test_title}</strong>
          <span className="muted">
            Question {attempt.position + 1} of {attempt.total_questions}
          </span>
        </div>
        <div className={`timer ${lowTime ? 'timer-low' : ''}`} role="timer" aria-label="Time left">
          <span className="timer-label" aria-hidden="true">Time left</span>
          <span className="timer-value tabular">{remaining == null ? '--:--' : formatDuration(remaining)}</span>
        </div>
        {/* Announce the one-minute warning once, rather than every tick. */}
        <span className="visually-hidden" aria-live="assertive">
          {lowTime ? 'One minute or less left' : ''}
        </span>
        <button className="btn btn-sm" onClick={() => setConfirmFinish(true)} disabled={submitting}>
          <span>
            Finish<span className="hide-phone"> test</span>
          </span>
        </button>
      </header>
      <ProgressBar
        className="test-progress"
        label="Progress through the test"
        value={(attempt.position / attempt.total_questions) * 100}
      />

      <main className={`container test-body ${q.type === 'code' ? 'test-body-wide' : ''}`}>
        <div className="question-meta">
          <span className="q-number">
            <b>{String(attempt.position + 1).padStart(2, '0')}</b> / {String(attempt.total_questions).padStart(2, '0')}
          </span>
          <span className="chip">{categoryLabel(q.category)}</span>
          <DifficultyTag level={q.difficulty} />
          <span className="muted">
            {q.points} point{q.points === 1 ? '' : 's'}
          </span>
        </div>

        {q.type === 'code' ? (
          <div className="code-layout">
            <div className="code-prompt">
              <Markdown>{q.prompt}</Markdown>
              <h3>Examples</h3>
              <ul className="examples">
                {q.examples?.map((ex, i) => (
                  <li key={i}>
                    <code>
                      {q.function_name}({ex.args.map((a) => formatValue(a)).join(', ')})
                    </code>{' '}
                    → <code>{formatValue(ex.expected)}</code>
                  </li>
                ))}
              </ul>
              <p className="muted small">+ {q.hidden_test_count} hidden tests used for scoring.</p>
            </div>
            <div className="code-work">
              <CodeEditor value={(draft as string) ?? ''} onChange={updateDraft} height="min(60vh, 520px)" />
              <div className="actions">
                <button className="btn" onClick={runCode} disabled={running || submitting}>
                  {running ? 'Running...' : 'Run examples'}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => updateDraft(q.starter_code ?? '')} disabled={running}>
                  Reset code
                </button>
              </div>
              {run && <RunPanel result={run} />}
            </div>
          </div>
        ) : (
          <div className="question-card">
            <Markdown>{q.prompt}</Markdown>
            {q.type === 'mcq' && (
              <div className="options" role="radiogroup">
                {q.options!.map((opt, i) => (
                  <label key={i} className={`option ${draft === i ? 'option-selected' : ''}`}>
                    <input
                      type="radio"
                      name={`q-${attempt.position}`}
                      checked={draft === i}
                      onChange={() => updateDraft(i)}
                      aria-label={`${String.fromCharCode(65 + i)}. ${opt}`}
                    />
                    <span className="option-letter">{String.fromCharCode(65 + i)}</span>
                    <Markdown inline>{opt}</Markdown>
                  </label>
                ))}
              </div>
            )}
            {q.type === 'written' && <WrittenAnswer q={q} value={(draft as string) ?? ''} onChange={updateDraft} />}
          </div>
        )}

        {actionError && <ErrorBox message={actionError} />}

        <div className="actions actions-end">
          <button className="btn btn-ghost" onClick={() => submit(true)} disabled={submitting}>
            Skip
          </button>
          <button className="btn btn-primary btn-lg" onClick={() => submit(false)} disabled={submitting || !answered}>
            {submitting ? 'Saving...' : isLast ? 'Submit & finish' : 'Save & next'}
          </button>
        </div>
        <p className="muted small center">You can't return to a question after moving on.</p>
      </main>

      {confirmFinish && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="finish-title">
          <div className="modal">
            <h2 id="finish-title">Finish the test now?</h2>
            <p className="muted">
              {attempt.total_questions - attempt.position - (answered ? 1 : 0)} question(s) will be left unanswered and
              score zero. Your current selection is saved. This can't be undone.
            </p>
            <div className="actions actions-end">
              <button className="btn btn-ghost" onClick={() => setConfirmFinish(false)}>
                Keep going
              </button>
              <button className="btn btn-danger" onClick={finishNow} disabled={submitting}>
                Finish test
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function WrittenAnswer({ q, value, onChange }: { q: PublicQuestion; value: string; onChange: (v: string) => void }) {
  const words = wordCount(value)
  const min = q.min_words ?? 0
  const max = q.max_words ?? 400
  const state = words === 0 ? '' : words < min ? 'under' : words > max ? 'over' : 'ok'
  return (
    <div className="written">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={12}
        placeholder="Write your answer here..."
        spellCheck
      />
      <div className={`word-count word-${state}`}>
        {words} words · target {min}-{max}
        {state === 'under' && ' · too short'}
        {state === 'over' && ' · over the limit'}
      </div>
    </div>
  )
}

function RunPanel({ result }: { result: RunResult }) {
  return (
    <div className="run-panel">
      <div className={`run-summary ${result.passed === result.total && !result.error ? 'run-ok' : 'run-fail'}`}>
        {result.passed}/{result.total} example tests passed
      </div>
      {result.error && <pre className="run-error">{result.error}</pre>}
      {!result.error &&
        result.tests.map((t, i) => (
          <div key={i} className="run-case">
            <span className={t.passed ? 'pass' : 'fail'}>{t.passed ? '✓' : '✗'}</span>
            <div>
              <div>
                <span className="muted">input </span>
                <code>{(t.args as unknown[]).map((a) => formatValue(a)).join(', ')}</code>
              </div>
              <div>
                <span className="muted">expected </span>
                <code>{formatValue(t.expected)}</code>
                <span className="muted"> got </span>
                <code>{t.error ? t.error : formatValue(t.output)}</code>
              </div>
              {t.stdout && <pre className="stdout">{t.stdout}</pre>}
            </div>
          </div>
        ))}
    </div>
  )
}
