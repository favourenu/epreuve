import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, api } from '../api'
import { AuthShell } from '../components/AuthShell'
import { Logo, LogoMark } from '../components/Logo'
import { Card, EmptyState, ErrorBox, Spinner } from '../components/ui'
import { formatDay, formatNaira } from '../format'
import { useAsync } from '../hooks'
import type { Certificate } from '../types'

const STATUS_TEXT: Record<Certificate['status'], string> = {
  issued: 'Issued',
  under_review: 'Under review',
  awaiting_payment: 'Ready to claim',
  rejected: 'Not approved',
  revoked: 'Revoked',
}

const BADGE: Record<Certificate['status'], string> = {
  issued: 'badge-good',
  under_review: 'badge-ok',
  awaiting_payment: 'badge-ok',
  rejected: 'badge-bad',
  revoked: 'badge-bad',
}

/** Sends the user to Paystack to pay the certificate fee. */
export function ClaimButton({ cert, className = 'btn btn-sm btn-primary' }: { cert: Certificate; className?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function claim() {
    setBusy(true)
    setError(null)
    try {
      const { authorization_url } = await api.payForCertificate(cert.id)
      window.location.assign(authorization_url)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }
  return (
    <>
      <button className={className} onClick={claim} disabled={busy}>
        {busy ? 'Opening checkout...' : `Claim for ${formatNaira(cert.price_kobo ?? 0)}`}
      </button>
      {error && (
        <span className="small error-text" role="alert">
          {error}
        </span>
      )}
    </>
  )
}

function verifyUrl(code: string) {
  return `${window.location.origin}/verify/${code}`
}

function CopyLink({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      className="btn btn-sm"
      onClick={() =>
        navigator.clipboard.writeText(verifyUrl(code)).then(
          () => {
            setCopied(true)
            window.setTimeout(() => setCopied(false), 2000)
          },
          () => window.prompt('Copy this link:', verifyUrl(code)),
        )
      }
    >
      {copied ? 'Link copied' : 'Copy link'}
    </button>
  )
}

export function MyCertificates() {
  const { data, error, loading, reload } = useAsync(() => api.certificates(), [])
  if (loading) return <Spinner />
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">Proof of skill</p>
          <h1>Certificates</h1>
          <p className="muted">Earned on proctored certification attempts. Share the link with employers to verify them.</p>
        </div>
      </div>
      {data.length === 0 ? (
        <Card>
          <EmptyState
            icon="★"
            title="No certificates yet"
            action={
              <Link to="/dashboard" className="btn btn-primary">
                Choose an assessment
              </Link>
            }
          >
            Open any assessment and choose Certification. Score highly under proctored conditions to earn one.
          </EmptyState>
        </Card>
      ) : (
        <div className="cert-list">
          {data.map((c) => (
            <article key={c.id} className={`cert-row cert-${c.status}`}>
              <div className="cert-seal" aria-hidden="true">
                {c.level === 'distinction' ? 'D' : 'P'}
              </div>
              <div className="cert-row-main">
                <h2>{c.test_title}</h2>
                <p className="muted small">
                  {c.level === 'distinction' ? 'Distinction' : 'Pass'} · {Math.round(c.percent)}% ·{' '}
                  {c.issued_at ? `issued ${formatDay(c.issued_at)}` : `earned ${formatDay(c.created_at)}`} ·{' '}
                  <span className="tabular">{c.code}</span>
                </p>
                {c.status === 'under_review' && (
                  <p className="small">
                    Your attempt had integrity flags, so a person is reviewing it before the certificate is issued.
                  </p>
                )}
                {c.status === 'awaiting_payment' && (
                  <p className="small">
                    You passed. Pay the one-time {formatNaira(c.price_kobo ?? 0)} fee to issue it with a public link
                    employers can verify.
                  </p>
                )}
                {c.review_note && c.status !== 'issued' && <p className="small">Reviewer note: {c.review_note}</p>}
              </div>
              <div className="cert-row-actions">
                <span className={`badge ${BADGE[c.status]}`}>
                  {STATUS_TEXT[c.status]}
                </span>
                {c.status === 'issued' && (
                  <>
                    <Link className="btn btn-sm btn-primary" to={`/verify/${c.code}`}>
                      View
                    </Link>
                    <CopyLink code={c.code} />
                  </>
                )}
                {c.status === 'awaiting_payment' && <ClaimButton cert={c} />}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

/** Public: anyone can verify a certificate by its code. Printable. */
export function VerifyCertificate() {
  const { code = '' } = useParams()
  const { data, error, loading } = useAsync(
    () =>
      api.verifyCertificate(code).catch((e) => {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }),
    [code],
  )

  if (loading) {
    return (
      <AuthShell title="Checking certificate">
        <Spinner />
      </AuthShell>
    )
  }
  if (error) {
    return (
      <AuthShell title="Couldn't check this certificate">
        <ErrorBox message={error} />
      </AuthShell>
    )
  }
  if (!data) {
    return (
      <AuthShell title="Certificate not found">
        <EmptyState icon="?" title={`No certificate matches ${code.toUpperCase()}`} action={<VerifyForm />}>
          Check the code for typos. Codes look like EPR-ABCD-2345.
        </EmptyState>
      </AuthShell>
    )
  }

  return (
    <div className="verify-page">
      <div className={`verify-status ${data.valid ? 'verify-ok' : 'verify-bad'}`} role="status">
        {data.valid
          ? `Verified: this is a valid Épreuve certificate (${data.code}).`
          : `This certificate (${data.code}) has been revoked and is no longer valid.`}
      </div>
      <article className={`certificate ${data.valid ? '' : 'certificate-void'}`} aria-label="Certificate">
        <header className="certificate-head">
          <Logo />
          <span className="certificate-code tabular">{data.code}</span>
        </header>
        <p className="certificate-kicker">Certificate of {data.level === 'distinction' ? 'distinction' : 'achievement'}</p>
        <p className="certificate-presented">This certifies that</p>
        <h1 className="certificate-name">{data.holder_name}</h1>
        <p className="certificate-presented">
          passed the proctored <strong>{data.test_title}</strong> assessment with a score of{' '}
          <strong>{data.percent}%</strong>
          {data.level === 'distinction' ? ', with distinction' : ''}.
        </p>
        <footer className="certificate-foot">
          <div>
            <span className="stat-label">Issued</span>
            <strong>{data.issued_at ? formatDay(data.issued_at) : '-'}</strong>
          </div>
          <div className="certificate-seal" aria-hidden="true">
            <LogoMark size={56} />
          </div>
          <div>
            <span className="stat-label">Verify at</span>
            <strong className="certificate-url">{verifyUrl(data.code).replace(/^https?:\/\//, '')}</strong>
          </div>
        </footer>
      </article>
      <div className="actions no-print">
        <button className="btn btn-primary" onClick={() => window.print()}>
          Print or save as PDF
        </button>
        <Link to="/" className="btn btn-ghost">
          About Épreuve
        </Link>
      </div>
    </div>
  )
}

function VerifyForm() {
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    if (code.trim()) navigate(`/verify/${code.trim().toUpperCase()}`)
  }
  return (
    <form onSubmit={submit} className="form verify-form">
      <div className="field">
        <label htmlFor="cert-code">Certificate code</label>
        <input id="cert-code" placeholder="EPR-ABCD-2345" value={code} onChange={(e) => setCode(e.target.value)} required />
      </div>
      <button type="submit" className="btn btn-primary">
        Verify
      </button>
    </form>
  )
}

export function VerifyLookup() {
  return (
    <AuthShell title="Verify a certificate" intro="Enter the code printed on an Épreuve certificate.">
      <VerifyForm />
    </AuthShell>
  )
}

/** Paystack sends the user back here with ?reference=... after checkout. */
export function ClaimedPage() {
  const [params] = useSearchParams()
  const reference = params.get('reference') ?? params.get('trxref') ?? ''
  const [cert, setCert] = useState<Certificate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const asked = useRef(false)

  useEffect(() => {
    if (asked.current) return // React StrictMode runs effects twice in development
    asked.current = true
    if (!reference) {
      setError('This page needs a payment reference.')
      return
    }
    api.verifyPayment(reference).then(setCert, (e) => setError((e as Error).message))
  }, [reference])

  if (error) {
    return (
      <div className="narrow stack">
        <ErrorBox message={error} />
        <Link to="/certificates" className="btn">
          Back to certificates
        </Link>
      </div>
    )
  }
  if (!cert) return <Spinner />
  if (cert.status === 'issued') {
    return (
      <div className="narrow">
        <Card>
          <EmptyState
            icon="★"
            title="Your certificate is issued"
            action={
              <Link to={`/verify/${cert.code}`} className="btn btn-primary">
                View certificate
              </Link>
            }
          >
            Thank you. {cert.test_title} ({cert.level === 'distinction' ? 'distinction' : 'pass'}) is now public at its
            verification link, and you can print or save it as a PDF.
          </EmptyState>
        </Card>
      </div>
    )
  }
  return (
    <div className="narrow">
      <Card>
        <EmptyState
          icon="…"
          title="We haven't received the payment yet"
          action={
            <Link to="/certificates" className="btn btn-primary">
              Back to certificates
            </Link>
          }
        >
          If you completed the payment, it can take a minute to confirm; the certificate is issued automatically when
          it does. If you cancelled, you can claim it again from your certificates.
        </EmptyState>
      </Card>
    </div>
  )
}
