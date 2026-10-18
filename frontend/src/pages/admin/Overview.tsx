import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, ErrorBox, ScoreBadge, Spinner } from '../../components/ui'
import { formatNaira } from '../../format'
import { useAsync } from '../../hooks'
import { adminApi } from './adminApi'

function Stat({ label, value, to }: { label: string; value: number | string; to?: string }) {
  const body = (
    <>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </>
  )
  return to ? (
    <Link to={to} className="stat stat-link">
      {body}
    </Link>
  ) : (
    <div className="stat">{body}</div>
  )
}

export function OverviewPage() {
  const { data, error, loading, reload } = useAsync(() => adminApi.overview(), [])
  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null

  const chart = data.daily.map((d) => ({ ...d, day: d.date.slice(5) }))
  return (
    <div className="stack">
      <div className="stat-row admin-stats">
        <Stat label="Users" value={data.users_total} to="/admin/users" />
        <Stat label="New this week" value={data.users_new_7d} />
        <Stat label="Active this week" value={data.users_active_7d} />
        <Stat label="Taking a test now" value={data.attempts_in_progress} to="/admin/attempts?status=in_progress" />
        <Stat label="Completed this week" value={data.attempts_completed_7d} />
        <Stat label="Certificates issued" value={data.certificates_issued} to="/admin/certificates" />
        <Stat label="Awaiting review" value={data.certificates_pending_review} to="/admin/certificates" />
        <Stat label="Awaiting payment" value={data.certificates_awaiting_payment} />
        <Stat label={`Revenue (${data.payments} paid)`} value={formatNaira(data.revenue_kobo)} />
        <Stat label="Open invites" value={data.invites_open} to="/admin/invites" />
      </div>

      {data.certificates_pending_review > 0 && (
        <div className="banner banner-accent">
          <span>
            <strong>
              {data.certificates_pending_review === 1 ? '1 certificate needs' : `${data.certificates_pending_review} certificates need`} review
            </strong>{' '}
            because of integrity flags.
          </span>
          <Link to="/admin/certificates" className="btn btn-primary btn-sm">
            Review now
          </Link>
        </div>
      )}

      <div className="two-col">
        <Card title="Attempts, last 14 days">
          <div className="chart" role="img" aria-label="Attempts started and completed per day over the last 14 days">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: 'var(--muted)', fontSize: 11 }} stroke="var(--border)" />
                <YAxis allowDecimals={false} tick={{ fill: 'var(--muted)', fontSize: 12 }} stroke="var(--border)" />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }} />
                <Legend formatter={(value) => <span style={{ color: 'var(--text)' }}>{value}</span>} />
                <Bar dataKey="started" name="Started" fill="var(--mark)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="completed" name="Completed" fill="var(--brand)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card title="By assessment">
          {data.by_test.length === 0 ? (
            <p className="muted">No completed attempts yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Assessment</th>
                    <th>Completed</th>
                    <th>Average</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_test.map((t) => (
                    <tr key={t.test_id}>
                      <td>
                        <Link to={`/admin/leaderboard?test=${t.test_id}`}>{t.title}</Link>
                      </td>
                      <td className="tabular">{t.attempts}</td>
                      <td>
                        <ScoreBadge percent={t.average_percent} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
