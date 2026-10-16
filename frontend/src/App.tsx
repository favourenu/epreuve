import { NavLink, Route, Routes, Link } from 'react-router-dom'
import { Dashboard } from './pages/Dashboard'
import { History } from './pages/History'
import { Results } from './pages/Results'
import { TakeTest } from './pages/TakeTest'
import { TestIntro } from './pages/TestIntro'

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">É</span>
          Épreuve
        </Link>
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
      </header>
      <main className="container">{children}</main>
    </div>
  )
}

function NotFound() {
  return (
    <div className="card">
      <h1>Page not found</h1>
      <Link to="/">Back to dashboard</Link>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      {/* The test screen is full-focus, without navigation, like a real assessment. */}
      <Route path="/attempts/:attemptId" element={<TakeTest />} />
      <Route path="/" element={<Layout><Dashboard /></Layout>} />
      <Route path="/history" element={<Layout><History /></Layout>} />
      <Route path="/tests/:testId" element={<Layout><TestIntro /></Layout>} />
      <Route path="/attempts/:attemptId/results" element={<Layout><Results /></Layout>} />
      <Route path="*" element={<Layout><NotFound /></Layout>} />
    </Routes>
  )
}
