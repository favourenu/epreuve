import { Link, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { GuestOnly, RequireAuth, useAuth } from './auth'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { History } from './pages/History'
import { Results } from './pages/Results'
import { TakeTest } from './pages/TakeTest'
import { TestIntro } from './pages/TestIntro'

function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="user-menu">
      <span className="user-name" title={user.email}>
        {user.name}
      </span>
      <button className="btn btn-ghost btn-sm" onClick={() => logout()}>
        Log out
      </button>
    </div>
  )
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/dashboard" className="brand">
          <span className="brand-mark" aria-hidden="true">É</span>
          Épreuve
        </Link>
        <nav aria-label="Main">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <UserMenu />
      </header>
      <main className="container">{children}</main>
    </div>
  )
}

function NotFound() {
  return (
    <div className="card">
      <h1>Page not found</h1>
      <Link to="/">Back to the start</Link>
    </div>
  )
}

function Home() {
  const { user } = useAuth()
  if (user === undefined) return null
  return <Navigate to={user ? '/dashboard' : '/login'} replace />
}

const authed = (page: React.ReactNode, withLayout = true) => (
  <RequireAuth>{withLayout ? <Layout>{page}</Layout> : page}</RequireAuth>
)

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<GuestOnly><AuthPage mode="login" /></GuestOnly>} />
      <Route path="/signup" element={<GuestOnly><AuthPage mode="signup" /></GuestOnly>} />
      {/* The test screen is full-focus, without navigation, like a real assessment. */}
      <Route path="/attempts/:attemptId" element={authed(<TakeTest />, false)} />
      <Route path="/dashboard" element={authed(<Dashboard />)} />
      <Route path="/history" element={authed(<History />)} />
      <Route path="/tests/:testId" element={authed(<TestIntro />)} />
      <Route path="/attempts/:attemptId/results" element={authed(<Results />)} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
