import { Link, useLocation } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'
import { CategoryBars, Card, EmptyState, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { CATEGORY_TEST, categoryLabel, formatDate } from '../format'
import { useAsync } from '../hooks'
import type { TestSummary } from '../types'

const FEATURED_TEST = 'job-readiness'

function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function TestCard({ test, featured = false }: { test: TestSummary; featured?: boolean }) {
  return (
    <Link to={`/tests/${test.id}`} className={`test-card ${featured ? 'featured-test' : ''}`}>
      <div className="test-card-head">
        <h3>{test.title}</h3>
        {test.best_percent != null && <ScoreBadge percent={test.best_percent} />}
      </div>
      <p>{test.description}</p>
      <div className="test-meta">
        <span>{test.time_limit_minutes} min</span>
        <span>{test.question_count} questions</span>
        <span>{test.attempts ? `${test.attempts} attempt${test.attempts > 1 ? 's' : ''}` : 'Not tried yet'}</span>
        <span className="test-card-go" aria-hidden="true">
          {test.attempts ? 'Retake →' : 'Start →'}
        </span>
      </div>
    </Link>
  )
}

export function Dashboard() {
  const { user } = useAuth()
  const notice = (useLocation().state as { notice?: string } | null)?.notice
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.tests(), api.stats(), api.attempts('in_progress'), api.aiStatus()]),
    [],
  )

  if (loading && !data) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const [tests, stats, inProgress, ai] = data

  const featured = tests.find((t) => t.id === FEATURED_TEST)
  const weakest = stats.categories.find((c) => c.questions >= 3 && c.percent < 75)
  const recommended = weakest ? tests.find((t) => t.id === CATEGORY_TEST[weakest.category]) : undefined
  const groups = tests
    .filter((t) => t.id !== FEATURED_TEST)
    .reduce<Record<string, TestSummary[]>>((acc, t) => {
      ;(acc[t.skill_area] ??= []).push(t)
      return acc
    }, {})
  const chart = stats.history
    .filter((h) => h.percent != null)
    .map((h, i) => ({ n: i + 1, percent: h.percent, title: h.test_title, date: formatDate(h.started_at) }))
  const firstName = user?.name.split(' ')[0]
  const isNew = stats.completed_attempts === 0

  return (
    <div className="stack">
      <div className="page-head greeting">
        <div>
          <p className="eyebrow">{isNew ? 'Welcome to Épreuve' : 'Your practice'}</p>
          <h1>
            {greeting()}
            {firstName ? `, ${firstName}` : ''}.
          </h1>
          <p className="muted">
            {isNew
              ? 'Start with the full assessment to get a baseline, then drill the areas it flags.'
              : 'Timed, one question at a time, no going back.'}
          </p>
        </div>
        <span
          className={`chip ${ai.providers.length ? '' : 'chip-warn'}`}
          title={ai.providers.length ? 'AI feedback providers, in fallback order' : 'Add an API key in backend/.env to enable AI feedback'}
        >
          AI coach: {ai.providers.length ? ai.providers.map((p) => p.name).join(' → ') : 'not set up'}
        </span>
      </div>

      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}

      {inProgress.length > 0 && (
        <section className="stack-sm" aria-labelledby="running-title">
          <h2 id="running-title" className="section-title">
            In progress
          </h2>
          <div className="resume-list">
            {inProgress.map((a) => (
              <div className="banner" key={a.id}>
                <span>
                  <strong>{a.test_title}</strong>
                  <span className="muted"> · started {formatDate(a.started_at)}. The timer is still running.</span>
                </span>
                <Link className="btn btn-primary btn-sm" to={`/attempts/${a.id}`}>
                  Resume
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {!isNew && (
        <div className="stat-row">
          <div className="stat">
            <span className="stat-label">Tests completed</span>
            <span className="stat-value">{stats.completed_attempts}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Average score</span>
            <span className="stat-value">{stats.average_percent == null ? '-' : `${Math.round(stats.average_percent)}%`}</span>
          </div>
          <div className="stat">
            <span className="stat-label">Weakest area</span>
            <span className="stat-value stat-value-sm">{weakest ? categoryLabel(weakest.category) : 'None below 75%'}</span>
          </div>
        </div>
      )}

      {recommended && weakest && (
        <div className="banner banner-accent">
          <span>
            <strong>Practise next: {recommended.title}.</strong> Your {categoryLabel(weakest.category).toLowerCase()} score is{' '}
            {Math.round(weakest.percent)}%.
          </span>
          <Link className="btn btn-primary btn-sm" to={`/tests/${recommended.id}`}>
            Practise now
          </Link>
        </div>
      )}

      {featured && (
        <section className="stack-sm" aria-labelledby="featured-title">
          <h2 id="featured-title" className="section-title">
            Full assessment
          </h2>
          <TestCard test={featured} featured />
        </section>
      )}

      {Object.entries(groups).map(([area, list]) => (
        <section key={area} className="stack-sm" aria-label={area}>
          <h2 className="section-title">{area}</h2>
          <div className="test-grid">
            {list.map((t) => (
              <TestCard key={t.id} test={t} />
            ))}
          </div>
        </section>
      ))}

      <div className="two-col">
        <Card title="Score trend">
          {chart.length >= 2 ? (
            <div className="chart" role="img" aria-label={`Scores of your last ${chart.length} tests`}>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="n" tick={{ fill: 'var(--muted)', fontSize: 12 }} stroke="var(--border)" />
                  <YAxis domain={[0, 100]} tick={{ fill: 'var(--muted)', fontSize: 12 }} stroke="var(--border)" />
                  <Tooltip
                    contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}
                    labelFormatter={(_, p) => (p?.[0] ? `${p[0].payload.title} · ${p[0].payload.date}` : '')}
                    formatter={(v) => [`${v}%`, 'Score']}
                  />
                  <Line isAnimationActive={false} type="monotone" dataKey="percent" stroke="var(--brand)" strokeWidth={2.5} dot={{ r: 3.5, fill: 'var(--brand)' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyState icon="↗" title={isNew ? 'Your trend starts here' : 'One more test to go'}>
              {isNew
                ? 'Complete two tests and your scores will chart here, so you can see yourself improve.'
                : 'Complete one more test to see how your scores are moving.'}
            </EmptyState>
          )}
        </Card>
        <Card title="By skill">
          {stats.categories.length ? (
            <CategoryBars rows={stats.categories} />
          ) : (
            <EmptyState icon="%" title="No skills measured yet">
              Each test you finish adds to your accuracy for every skill it covers, weakest first.
            </EmptyState>
          )}
        </Card>
      </div>
    </div>
  )
}
