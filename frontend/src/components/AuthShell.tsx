import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from './Logo'

/** Centered card layout shared by log in, sign up and password pages. */
export function AuthShell({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <div className="auth-page">
      <Link to="/" className="brand auth-brand" aria-label="Épreuve home">
        <Logo />
      </Link>
      <div className="auth-card">
        <h1>{title}</h1>
        {intro && <p className="muted">{intro}</p>}
        {children}
      </div>
    </div>
  )
}
