import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { GuestOnly, RequireAuth, useAuth } from './auth'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { Landing } from './pages/Landing'
import { Logo } from './components/Logo'
import { EmptyState } from './components/ui'
import { History } from './pages/History'
import { ClaimedPage, MyCertificates, VerifyCertificate, VerifyLookup } from './pages/CertificatePages'
import { ContactPage, PrivacyPage, RefundsPage, TermsPage } from './pages/LegalPages'
import { SiteFooter } from './components/SiteFooter'
import { InvitePage, SubmittedPage } from './pages/InvitePages'
import { AdminPage } from './pages/admin/AdminPage'
import { ForgotPassword, ResetPassword } from './pages/PasswordPages'
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

function AdminLink() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <NavLink to="/admin">Admin</NavLink> : null
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  if (user?.role !== 'admin') return <NotFound />
  return <>{children}</>
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/dashboard" className="brand">
          <Logo />
        </Link>
        <nav aria-label="Main">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/history">History</NavLink>
          <NavLink to="/certificates">Certificates</NavLink>
          <AdminLink />
        </nav>
        <UserMenu />
      </header>
      <main className="container">{children}</main>
      <SiteFooter />
    </div>
  )
}

function NotFound() {
  return (
    <div className="auth-page">
      <Link to="/" className="brand" aria-label="Épreuve home">
        <Logo />
      </Link>
      <div className="auth-card">
        <EmptyState
          icon="?"
          title="This page doesn't exist"
          action={
            <Link to="/" className="btn btn-primary">
              Go to the start
            </Link>
          }
        >
          The link may be mistyped, or the page may have moved.
        </EmptyState>
      </div>
    </div>
  )
}

const authed = (page: React.ReactNode, withLayout = true) => (
  <RequireAuth>{withLayout ? <Layout>{page}</Layout> : page}</RequireAuth>
)

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<GuestOnly><Landing /></GuestOnly>} />
      <Route path="/login" element={<GuestOnly><AuthPage mode="login" /></GuestOnly>} />
      <Route path="/signup" element={<GuestOnly><AuthPage mode="signup" /></GuestOnly>} />
      <Route path="/forgot-password" element={<GuestOnly><ForgotPassword /></GuestOnly>} />
      {/* Not guest-only: a signed-in user following a reset link should still be able to use it. */}
      <Route path="/reset-password" element={<ResetPassword />} />
      {/* The test screen is full-focus, without navigation, like a real assessment. */}
      <Route path="/attempts/:attemptId" element={authed(<TakeTest />, false)} />
      <Route path="/dashboard" element={authed(<Dashboard />)} />
      <Route path="/history" element={authed(<History />)} />
      <Route path="/tests/:testId" element={authed(<TestIntro />)} />
      <Route path="/attempts/:attemptId/results" element={authed(<Results />)} />
      <Route path="/attempts/:attemptId/submitted" element={authed(<SubmittedPage />, false)} />
      <Route path="/certificates" element={authed(<MyCertificates />)} />
      {/* Paystack returns here after checkout. */}
      <Route path="/certificates/claimed" element={authed(<ClaimedPage />)} />
      <Route path="/admin/*" element={authed(<AdminOnly><AdminPage /></AdminOnly>)} />
      {/* Public pages: certificate verification and company invitations. */}
      <Route path="/verify" element={<VerifyLookup />} />
      <Route path="/verify/:code" element={<VerifyCertificate />} />
      <Route path="/invite/:token" element={<InvitePage />} />
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/refunds" element={<RefundsPage />} />
      <Route path="/contact" element={<ContactPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
