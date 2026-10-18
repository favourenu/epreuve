import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorBox, Spinner } from '../../components/ui'
import { formatDate } from '../../format'
import { useAsync } from '../../hooks'
import type { CertificateStatus } from '../../types'
import { adminApi, type AdminCertificate } from './adminApi'
import { RiskBadge } from './shared'

const FILTERS: { value: CertificateStatus | ''; label: string }[] = [
  { value: 'under_review', label: 'Needs review' },
  { value: 'issued', label: 'Issued' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'revoked', label: 'Revoked' },
  { value: '', label: 'All' },
]

type Action = 'approve' | 'reject' | 'revoke' | 'reinstate'
const ACTIONS: Record<CertificateStatus, { action: Action; label: string; danger?: boolean }[]> = {
  under_review: [
    { action: 'approve', label: 'Approve' },
    { action: 'reject', label: 'Reject', danger: true },
  ],
  issued: [{ action: 'revoke', label: 'Revoke', danger: true }],
  rejected: [{ action: 'approve', label: 'Approve' }],
  revoked: [{ action: 'reinstate', label: 'Reinstate' }],
}

function Row({ cert, onChanged }: { cert: AdminCertificate; onChanged: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function act(action: Action) {
    setBusy(true)
    setError(null)
    try {
      await adminApi.reviewCertificate(cert.id, action, note || undefined)
      onChanged()
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <article className="review-card">
      <div className="review-card-head">
        <div>
          <h3>
            {cert.user.name} · {cert.test_title}
          </h3>
          <p className="muted small">
            {cert.user.email} · {Math.round(cert.percent)}% ({cert.level}) · <span className="tabular">{cert.code}</span> ·{' '}
            {formatDate(cert.created_at)}
          </p>
        </div>
        <RiskBadge risk={cert.integrity.risk} />
      </div>
      {cert.integrity.reasons.length > 0 && (
        <ul className="reasons">
          {cert.integrity.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {cert.review_note && <p className="small">Note: {cert.review_note}</p>}
      <div className="review-card-actions">
        <Link to={`/admin/attempts/${cert.attempt_id}`} className="btn btn-sm">
          See attempt and events
        </Link>
        <input
          aria-label={`Review note for ${cert.user.name}`}
          placeholder="Note (optional, shown to the candidate)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        {ACTIONS[cert.status].map((a) => (
          <button key={a.action} className={`btn btn-sm ${a.danger ? 'btn-danger' : 'btn-primary'}`} disabled={busy} onClick={() => act(a.action)}>
            {a.label}
          </button>
        ))}
      </div>
      {error && <ErrorBox message={error} />}
    </article>
  )
}

export function CertificatesQueue() {
  const [status, setStatus] = useState<CertificateStatus | ''>('under_review')
  const { data, error, loading, reload } = useAsync(() => adminApi.certificates(status), [status])

  return (
    <Card>
      <div className="segmented" role="group" aria-label="Filter certificates">
        {FILTERS.map((f) => (
          <button key={f.label} className={status === f.value ? 'active' : ''} onClick={() => setStatus(f.value)}>
            {f.label}
          </button>
        ))}
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading && !data ? (
        <Spinner />
      ) : data && data.length === 0 ? (
        <EmptyState icon="✓" title={status === 'under_review' ? 'Nothing to review' : 'No certificates here'}>
          {status === 'under_review' ? 'Certificates with integrity flags will appear here for a decision.' : ''}
        </EmptyState>
      ) : (
        <div className="review-cards">
          {data?.map((c) => (
            <Row key={c.id} cert={c} onChanged={reload} />
          ))}
        </div>
      )}
    </Card>
  )
}
