import { Link } from 'react-router-dom'
import { api } from '../api'
import { Card, EmptyState, ErrorBox, ScoreBadge, Spinner } from '../components/ui'
import { formatDate, formatDuration } from '../format'
import { useAsync } from '../hooks'

export function History() {
  const { data, error, loading, reload } = useAsync(() => api.attempts(), [])

  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">Every attempt</p>
          <h1>History</h1>
        </div>
      </div>
      <Card>
        {data.length === 0 ? (
          <EmptyState
            icon="⏱"
            title="No attempts yet"
            action={
              <Link to="/dashboard" className="btn btn-primary">
                Choose a test
              </Link>
            }
          >
            Every test you take is saved here with its score, so you can review your answers and see your progress.
          </EmptyState>
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
                    <td>
                      {a.test_title}
                      {a.mode !== 'practice' && (
                        <span className={`mode-chip mode-${a.mode}`}>
                          {a.mode === 'certification' ? 'Certification' : `For ${a.company ?? 'a company'}`}
                        </span>
                      )}
                    </td>
                    <td className="muted">{formatDate(a.started_at)}</td>
                    <td className="muted tabular">
                      {a.submitted_at
                        ? formatDuration((new Date(a.submitted_at).getTime() - new Date(a.started_at).getTime()) / 1000)
                        : '-'}
                      {a.timed_out && ' (timed out)'}
                    </td>
                    <td>
                      {a.status !== 'completed' ? (
                        <span className="chip">In progress</span>
                      ) : a.mode === 'invite' ? (
                        <span className="chip">Submitted</span>
                      ) : (
                        <ScoreBadge percent={a.percent} />
                      )}
                    </td>
                    <td className="right">
                      <Link
                        className="btn btn-sm"
                        to={
                          a.status !== 'completed'
                            ? `/attempts/${a.id}`
                            : a.mode === 'invite'
                              ? `/attempts/${a.id}/submitted`
                              : `/attempts/${a.id}/results`
                        }
                        aria-label={`${a.status === 'completed' ? 'Review' : 'Resume'} ${a.test_title}, ${formatDate(a.started_at)}`}
                      >
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
