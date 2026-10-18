import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api'
import { Card, EmptyState, ErrorBox, ScoreBadge, Spinner } from '../../components/ui'
import { formatDate } from '../../format'
import { useAsync } from '../../hooks'
import { adminApi, type InviteRow } from './adminApi'
import { RiskBadge } from './shared'

const STATUS_TEXT: Record<InviteRow['status'], string> = {
  sent: 'Sent',
  opened: 'Opened',
  in_progress: 'In progress',
  completed: 'Completed',
  expired: 'Expired',
  cancelled: 'Withdrawn',
}

function InviteForm({ onCreated }: { onCreated: (row: InviteRow) => void }) {
  const tests = useAsync(() => api.tests(), [])
  const [form, setForm] = useState({ candidate_name: '', email: '', company: '', test_id: '', message: '', valid_days: 14 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const row = await adminApi.createInvite({
        ...form,
        message: form.message.trim() || undefined,
        valid_days: Number(form.valid_days) || undefined,
      })
      onCreated(row)
      setForm({ ...form, candidate_name: '', email: '', message: '' })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form invite-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="inv-name">Candidate name</label>
        <input id="inv-name" required maxLength={100} value={form.candidate_name} onChange={set('candidate_name')} />
      </div>
      <div className="field">
        <label htmlFor="inv-email">Candidate email</label>
        <input id="inv-email" type="email" required value={form.email} onChange={set('email')} />
      </div>
      <div className="field">
        <label htmlFor="inv-company">Company</label>
        <input id="inv-company" required maxLength={120} value={form.company} onChange={set('company')} />
      </div>
      <div className="field">
        <label htmlFor="inv-test">Assessment</label>
        <select id="inv-test" required value={form.test_id} onChange={set('test_id')}>
          <option value="" disabled>
            Choose an assessment
          </option>
          {tests.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title} ({t.time_limit_minutes} min)
            </option>
          ))}
        </select>
      </div>
      <div className="field invite-form-wide">
        <label htmlFor="inv-message">Message to the candidate (optional)</label>
        <textarea id="inv-message" rows={3} maxLength={1000} value={form.message} onChange={set('message')} />
      </div>
      <div className="field">
        <label htmlFor="inv-days">Link valid for (days)</label>
        <input id="inv-days" type="number" min={1} max={90} value={form.valid_days} onChange={set('valid_days')} />
      </div>
      {error && <div className="invite-form-wide"><ErrorBox message={error} /></div>}
      <div className="invite-form-wide">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Sending...' : 'Send invitation'}
        </button>
      </div>
    </form>
  )
}

export function Invites() {
  const [company, setCompany] = useState('')
  const [created, setCreated] = useState<InviteRow | null>(null)
  const [copied, setCopied] = useState(false)
  const { data, error, loading, reload } = useAsync(() => adminApi.invites(company.trim() || undefined), [company])

  async function cancel(row: InviteRow) {
    if (!window.confirm(`Withdraw ${row.candidate_name}'s invitation?`)) return
    await adminApi.cancelInvite(row.id).catch((e) => window.alert((e as Error).message))
    reload()
  }

  return (
    <div className="stack">
      <Card title="Invite a candidate">
        <p className="muted">
          The candidate gets an email with a private link. They take the assessment proctored, with one attempt, and
          only you see the results.
        </p>
        <InviteForm
          onCreated={(row) => {
            setCreated(row)
            setCopied(false)
            reload()
          }}
        />
        {created?.link && (
          <div className="notice" role="status">
            <p>
              Invitation sent to <strong>{created.email}</strong>. You can also share this link directly (it's shown only
              once):
            </p>
            <div className="copy-row">
              <code>{created.link}</code>
              <button
                className="btn btn-sm"
                onClick={() => navigator.clipboard.writeText(created.link!).then(() => setCopied(true))}
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Candidates"
        actions={
          <a className="btn btn-sm" href={adminApi.invitesCsvUrl(company.trim() || undefined)} download>
            Export CSV
          </a>
        }
      >
        <div className="admin-toolbar">
          <div className="field">
            <label htmlFor="inv-filter">Filter by company</label>
            <input id="inv-filter" placeholder="All companies" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
        </div>
        {error && <ErrorBox message={error} onRetry={reload} />}
        {loading && !data ? (
          <Spinner />
        ) : data && data.length === 0 ? (
          <EmptyState icon="✉" title="No invitations yet">Invite a candidate above to get started.</EmptyState>
        ) : data ? (
          <div className="table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Company</th>
                  <th>Assessment</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Integrity</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.candidate_name}
                      <div className="muted small">{r.email}</div>
                    </td>
                    <td>{r.company}</td>
                    <td>{r.test_title}</td>
                    <td>
                      {STATUS_TEXT[r.status]}
                      <div className="muted small">
                        {r.submitted_at ? `submitted ${formatDate(r.submitted_at)}` : `expires ${formatDate(r.expires_at)}`}
                      </div>
                    </td>
                    <td>{r.percent == null ? <span className="muted">-</span> : <ScoreBadge percent={r.percent} />}</td>
                    <td>
                      <RiskBadge risk={r.risk} />
                    </td>
                    <td className="right">
                      {r.attempt_id ? (
                        <Link className="btn btn-sm" to={`/admin/attempts/${r.attempt_id}`}>
                          Open
                        </Link>
                      ) : r.status === 'sent' || r.status === 'opened' ? (
                        <button className="btn btn-sm btn-ghost" onClick={() => cancel(r)}>
                          Withdraw
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  )
}
