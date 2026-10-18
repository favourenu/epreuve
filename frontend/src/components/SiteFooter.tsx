import { Link } from 'react-router-dom'
import { Logo } from './Logo'

export const SUPPORT_EMAIL = 'support@epreuve.site'

/** Slim footer for the public and signed-in pages (not the test screen). */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <Link to="/" className="brand" aria-label="Épreuve home">
          <Logo size={20} />
        </Link>
        <nav aria-label="Footer">
          <Link to="/verify">Verify a certificate</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/refunds">Refunds</Link>
          <Link to="/contact">Contact</Link>
          <a href="/api/docs">API</a>
        </nav>
        <span className="muted small">© {new Date().getFullYear()} Épreuve</span>
      </div>
    </footer>
  )
}
