import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { Card, EmptyState, ErrorBox, ScoreBadge, Spinner } from '../../components/ui'
import { useAsync } from '../../hooks'
import { adminApi } from './adminApi'

export function Leaderboard() {
  const [params] = useSearchParams()
  const [testId, setTestId] = useState(params.get('test') ?? '')
  const [period, setPeriod] = useState('all')
  const [mode, setMode] = useState('all')
  const tests = useAsync(() => api.tests(), [])
  const { data, error, loading, reload } = useAsync(
    () => adminApi.leaderboard({ test_id: testId || undefined, period, mode }),
    [testId, period, mode],
  )

  return (
    <Card>
      <div className="admin-toolbar">
        <div className="field">
          <label htmlFor="lb-test">Assessment</label>
          <select id="lb-test" value={testId} onChange={(e) => setTestId(e.target.value)}>
            <option value="">All assessments (average of best scores)</option>
            {tests.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="lb-period">Period</label>
          <select id="lb-period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="all">All time</option>
            <option value="30d">Last 30 days</option>
            <option value="7d">Last 7 days</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="lb-mode">Attempts</label>
          <select id="lb-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="all">Practice and certification</option>
            <option value="certification">Certification only</option>
          </select>
        </div>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <EmptyState icon="#" title="No scores yet">Completed attempts will rank here.</EmptyState>
      ) : data ? (
        <div className="table-wrap">
          <table className="admin-table leaderboard">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Candidate</th>
                <th>{testId ? 'Best score' : 'Average best'}</th>
                <th>Assessments</th>
                <th>Attempts</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.user.id}>
                  <td className={`rank rank-${r.rank}`}>{r.rank}</td>
                  <td>
                    <Link to={`/admin/users/${r.user.id}`}>{r.user.name}</Link>
                    <div className="muted small">{r.user.email}</div>
                  </td>
                  <td>
                    <ScoreBadge percent={r.score} />
                  </td>
                  <td className="tabular">{r.tests_taken}</td>
                  <td className="tabular">{r.attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  )
}
