import { Link } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { CategoryBars, Card, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { CATEGORY_TEST, categoryLabel, formatDate } from '../format'
import { useAsync } from '../hooks'
import type { TestSummary } from '../types'

export function Dashboard() {
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.tests(), api.stats(), api.attempts('in_progress'), api.aiStatus()]),
    [],
  )

  if (loading && !data) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const [tests, stats, inProgress, ai] = data

  const weakest = stats.categories.find((c) => c.questions >= 3 && c.percent < 75)
  const recommended = weakest ? tests.find((t) => t.id === CATEGORY_TEST[weakest.category]) : undefined
  const groups = tests.reduce<Record<string, TestSummary[]>>((acc, t) => {
    ;(acc[t.skill_area] ??= []).push(t)
    return acc
  }, {})
  const chart = stats.history
    .filter((h) => h.percent != null)
    .map((h, i) => ({ n: i + 1, percent: h.percent, title: h.test_title, date: formatDate(h.started_at) }))

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Dashboard</h1>
          <p className="muted">Practise under real conditions: timed, one question at a time, no going back.</p>
        </div>
        <span className={`chip ${ai.providers.length ? '' : 'chip-warn'}`} title="AI providers, in fallback order">
          AI: {ai.providers.length ? ai.providers.map((p) => p.name).join(' → ') : 'not configured'}
        </span>
      </div>

      {inProgress.map((a) => (
        <div className="banner" key={a.id}>
          <span>
            <strong>{a.test_title}</strong> is still in progress (the timer is running).
          </span>
          <Link className="btn btn-primary btn-sm" to={`/attempts/${a.id}`}>
            Resume
          </Link>
        </div>
      ))}

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
          <span className="stat-value stat-value-sm">{weakest ? categoryLabel(weakest.category) : '-'}</span>
        </div>
      </div>

      {recommended && (
        <div className="banner banner-accent">
          <span>
            <strong>Recommended next:</strong> {recommended.title}. Your {categoryLabel(weakest!.category).toLowerCase()} score is{' '}
            {Math.round(weakest!.percent)}%.
          </span>
          <Link className="btn btn-primary btn-sm" to={`/tests/${recommended.id}`}>
            Practise
          </Link>
        </div>
      )}

      {Object.entries(groups).map(([area, list]) => (
        <section key={area} className="stack-sm">
          <h2 className="section-title">{area}</h2>
          <div className="test-grid">
            {list.map((t) => (
              <Link key={t.id} to={`/tests/${t.id}`} className="test-card">
                <div className="test-card-head">
                  <h3>{t.title}</h3>
                  {t.best_percent != null && <ScoreBadge percent={t.best_percent} />}
                </div>
                <p className="muted">{t.description}</p>
                <div className="test-meta">
                  <span>{t.time_limit_minutes} min</span>
                  <span>{t.question_count} questions</span>
                  <span>{t.attempts ? `${t.attempts} attempt${t.attempts > 1 ? 's' : ''}` : 'Not attempted'}</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}

      {stats.completed_attempts > 0 && (
        <div className="two-col">
          <Card title="Score trend">
            {chart.length >= 2 ? (
              <div className="chart">
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={chart} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="n" tick={{ fill: 'var(--muted)', fontSize: 12 }} stroke="var(--border)" />
                    <YAxis domain={[0, 100]} tick={{ fill: 'var(--muted)', fontSize: 12 }} stroke="var(--border)" />
                    <Tooltip
                      contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                      labelFormatter={(_, p) => (p?.[0] ? `${p[0].payload.title} · ${p[0].payload.date}` : '')}
                      formatter={(v) => [`${v}%`, 'Score']}
                    />
                    <Line type="monotone" dataKey="percent" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="muted">Complete one more test to see your trend.</p>
            )}
          </Card>
          <Card title="By skill (all attempts)">
            <CategoryBars rows={stats.categories} />
          </Card>
        </div>
      )}
    </div>
  )
}
