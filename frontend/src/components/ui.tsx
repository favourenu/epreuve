import type { ReactNode } from 'react'
import { categoryLabel, scoreTone } from '../format'

export function ScoreBadge({ percent }: { percent: number | null | undefined }) {
  const tone = scoreTone(percent)
  return <span className={`badge badge-${tone}`}>{percent == null ? '-' : `${Math.round(percent)}%`}</span>
}

export function ProgressBar({ value, tone }: { value: number; tone?: string }) {
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div className="bar" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`bar-fill ${tone ? `bar-${tone}` : ''}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function CategoryBars({
  rows,
}: {
  rows: { category: string; percent: number; points: number; max_points: number; pending?: boolean }[]
}) {
  return (
    <ul className="cat-bars">
      {rows.map((r) => (
        <li key={r.category}>
          <div className="cat-bars-head">
            <span>{categoryLabel(r.category)}</span>
            <span className="muted tabular">
              {r.pending ? 'awaiting AI grading' : `${r.points.toFixed(r.points % 1 ? 1 : 0)}/${r.max_points} · ${Math.round(r.percent)}%`}
            </span>
          </div>
          <ProgressBar value={r.pending ? 0 : r.percent} tone={scoreTone(r.percent)} />
        </li>
      ))}
    </ul>
  )
}

export function Card({ title, actions, children, className = '' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button className="btn btn-ghost btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="spinner-row" role="status">
      <span className="spinner" aria-hidden="true" />
      <span className="muted">{label}...</span>
    </div>
  )
}

export function DifficultyTag({ level }: { level: string }) {
  return <span className={`tag tag-${level}`}>{level}</span>
}
