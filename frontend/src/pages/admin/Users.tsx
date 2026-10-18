import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Card, EmptyState, ErrorBox, ScoreBadge, Spinner } from '../../components/ui'
import { formatDate } from '../../format'
import { useAsync } from '../../hooks'
import { adminApi } from './adminApi'
import { AttemptsTable, Pager } from './shared'

const PAGE = 25

export function UsersList() {
  const [query, setQuery] = useState('')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const { data, error, loading, reload } = useAsync(() => adminApi.users(q, PAGE, offset), [q, offset])

  // Search as you type, after a short pause.
  useEffect(() => {
    const t = window.setTimeout(() => {
      setQ(query.trim())
      setOffset(0)
    }, 300)
    return () => window.clearTimeout(t)
  }, [query])

  return (
    <Card>
      <div className="admin-toolbar">
        <div className="field">
          <label htmlFor="user-search">Search users</label>
          <input id="user-search" type="search" placeholder="Name or email" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {data && <span className="muted small">{data.total} user(s)</span>}
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Spinner />
      ) : data && data.users.length === 0 ? (
        <EmptyState icon="?" title="No users match">Try part of a name or email address.</EmptyState>
      ) : data ? (
        <>
          <div className="table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Joined</th>
                  <th>Completed</th>
                  <th>Average</th>
                  <th>Certificates</th>
                  <th>Last active</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <Link to={`/admin/users/${u.id}`}>{u.name}</Link>
                      {u.role === 'admin' && <span className="mode-chip mode-certification">Admin</span>}
                      {u.disabled && <span className="mode-chip">Suspended</span>}
                      <div className="muted small">{u.email}</div>
                    </td>
                    <td className="muted small">{formatDate(u.created_at)}</td>
                    <td className="tabular">{u.attempts_completed}</td>
                    <td>{u.average_percent == null ? <span className="muted">-</span> : <ScoreBadge percent={u.average_percent} />}</td>
                    <td className="tabular">{u.certificates}</td>
                    <td className="muted small">{u.last_active ? formatDate(u.last_active) : 'Never'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={data.total} limit={PAGE} offset={offset} onChange={setOffset} />
        </>
      ) : null}
    </Card>
  )
}

export function UserDetail() {
  const { userId = '' } = useParams()
  const { data, error, loading, reload, setData } = useAsync(() => adminApi.user(userId), [userId])
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (loading && !data) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null
  const { user } = data

  async function update(patch: { role?: 'user' | 'admin'; disabled?: boolean }, confirmText: string) {
    if (!window.confirm(confirmText)) return
    setBusy(true)
    setActionError(null)
    try {
      const updated = await adminApi.updateUser(user.id, patch)
      setData({ ...data!, user: updated })
    } catch (e) {
      setActionError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <Link to="/admin/users" className="back">
        ← Users
      </Link>
      <Card>
        <div className="admin-user-head">
          <div>
            <h2>
              {user.name}
              {user.role === 'admin' && <span className="mode-chip mode-certification">Admin</span>}
              {user.disabled && <span className="mode-chip">Suspended</span>}
            </h2>
            <p className="muted">
              {user.email} · joined {formatDate(user.created_at)}
            </p>
          </div>
          <div className="actions">
            <button
              className="btn btn-sm"
              disabled={busy}
              onClick={() =>
                user.role === 'admin'
                  ? update({ role: 'user' }, `Remove admin access from ${user.name}?`)
                  : update({ role: 'admin' }, `Give ${user.name} full admin access?`)
              }
            >
              {user.role === 'admin' ? 'Remove admin' : 'Make admin'}
            </button>
            <button
              className={`btn btn-sm ${user.disabled ? '' : 'btn-danger'}`}
              disabled={busy}
              onClick={() =>
                user.disabled
                  ? update({ disabled: false }, `Restore ${user.name}'s account?`)
                  : update({ disabled: true }, `Suspend ${user.name}? They'll be signed out and unable to log in.`)
              }
            >
              {user.disabled ? 'Restore account' : 'Suspend account'}
            </button>
          </div>
        </div>
        {actionError && <ErrorBox message={actionError} />}
      </Card>

      <Card title={`Attempts (${data.attempts.length})`}>
        <AttemptsTable rows={data.attempts} showUser={false} />
      </Card>

      <Card title={`Certificates (${data.certificates.length})`}>
        {data.certificates.length === 0 ? (
          <p className="muted">No certificates.</p>
        ) : (
          <ul className="plain-list">
            {data.certificates.map((c) => (
              <li key={c.id}>
                <strong>{c.test_title}</strong> · {c.level} · {Math.round(c.percent)}% ·{' '}
                <span className="tabular">{c.code}</span> · {c.status.replace('_', ' ')}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
