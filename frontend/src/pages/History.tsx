import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { formatDate, formatDuration } from '../format'
import { useAsync } from '../hooks'

export function History() {
  const { data, error, loading, reload } = useAsync(() => api.attempts(), [])

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="stack">
      <h1>History</h1>
      <Card>
        {data.length === 0 ? (
          <p className="muted">
            No attempts yet. <Link to="/">Pick a test</Link> to get started.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Date</th>
                  <th>Time used</th>
                  <th>Score</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id}>
                    <td>{a.test_title}</td>
                    <td className="muted">{formatDate(a.started_at)}</td>
                    <td className="muted tabular">
                      {a.submitted_at
                        ? formatDuration((new Date(a.submitted_at).getTime() - new Date(a.started_at).getTime()) / 1000)
                        : '-'}
                      {a.timed_out && ' (timed out)'}
                    </td>
                    <td>{a.status === 'completed' ? <ScoreBadge percent={a.percent} /> : <span className="chip">In progress</span>}</td>
                    <td className="right">
                      <Link to={a.status === 'completed' ? `/attempts/${a.id}/results` : `/attempts/${a.id}`}>
                        {a.status === 'completed' ? 'Review' : 'Resume'}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
