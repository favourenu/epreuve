import { Link } from 'react-router-dom'
import { ScoreBadge } from '../../components/ui'
import { formatDate } from '../../format'
import type { AttemptMode } from '../../types'
import type { AdminAttemptRow, Risk } from './adminApi'

const RISK_TEXT: Record<Risk, string> = { none: 'Clean', low: 'Minor flags', high: 'Flagged' }

export function RiskBadge({ risk }: { risk: Risk | null }) {
  if (!risk) return <span className="muted small">-</span>
  const tone = risk === 'high' ? 'badge-bad' : risk === 'low' ? 'badge-ok' : 'badge-good'
  return <span className={`badge ${tone}`}>{RISK_TEXT[risk]}</span>
}

export function ModeLabel({ mode, company }: { mode: AttemptMode; company?: string | null }) {
  if (mode === 'practice') return <span className="muted small">Practice</span>
  if (mode === 'certification') return <span className="mode-chip mode-certification">Certification</span>
  return <span className="mode-chip">For {company ?? 'company'}</span>
}

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
}) {
  if (total <= limit) return null
  return (
    <div className="pager">
      <button className="btn btn-sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Previous
      </button>
      <span className="muted small tabular">
        {offset + 1}-{Math.min(total, offset + limit)} of {total}
      </span>
      <button className="btn btn-sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
        Next
      </button>
    </div>
  )
}

/** Attempts table used on the attempts list and a user's page. */
export function AttemptsTable({ rows, showUser = true }: { rows: AdminAttemptRow[]; showUser?: boolean }) {
  if (rows.length === 0) return <p className="muted">No attempts match.</p>
  return (
    <div className="table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            {showUser && <th>Candidate</th>}
            <th>Assessment</th>
            <th>Type</th>
            <th>Started</th>
            <th>Score</th>
            <th>Integrity</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              {showUser && (
                <td>
                  <Link to={`/admin/users/${a.user.id}`}>{a.user.name}</Link>
                  <div className="muted small">{a.user.email}</div>
                </td>
              )}
              <td>{a.test_title}</td>
              <td>
                <ModeLabel mode={a.mode} company={a.company} />
              </td>
              <td className="muted small">{formatDate(a.started_at)}</td>
              <td>{a.status === 'completed' ? <ScoreBadge percent={a.percent} /> : <span className="chip">In progress</span>}</td>
              <td>
                <RiskBadge risk={a.risk} />
              </td>
              <td className="right">
                <Link className="btn btn-sm" to={`/admin/attempts/${a.id}`} aria-label={`Open ${a.user.name}'s ${a.test_title} attempt`}>
                  Open
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
