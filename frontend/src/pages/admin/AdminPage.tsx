import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { AttemptDetail, AttemptsList } from './Attempts'
import { CertificatesQueue } from './Certificates'
import { Invites } from './Invites'
import { Leaderboard } from './Leaderboard'
import { OverviewPage } from './Overview'
import { UserDetail, UsersList } from './Users'

const TABS = [
  { to: 'overview', label: 'Overview' },
  { to: 'users', label: 'Users' },
  { to: 'attempts', label: 'Attempts' },
  { to: 'leaderboard', label: 'Leaderboard' },
  { to: 'certificates', label: 'Certificates' },
  { to: 'invites', label: 'Company invites' },
]

export function AdminPage() {
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="eyebrow">Admin</p>
          <h1>Épreuve admin</h1>
        </div>
      </div>
      <nav className="admin-tabs" aria-label="Admin sections">
        {TABS.map((t) => (
          <NavLink key={t.to} to={`/admin/${t.to}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="overview" replace />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="users" element={<UsersList />} />
        <Route path="users/:userId" element={<UserDetail />} />
        <Route path="attempts" element={<AttemptsList />} />
        <Route path="attempts/:attemptId" element={<AttemptDetail />} />
        <Route path="leaderboard" element={<Leaderboard />} />
        <Route path="certificates" element={<CertificatesQueue />} />
        <Route path="invites" element={<Invites />} />
        <Route path="*" element={<Navigate to="overview" replace />} />
      </Routes>
    </div>
  )
}
