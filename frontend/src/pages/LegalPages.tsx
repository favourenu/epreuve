import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { Logo } from '../components/Logo'
import { SiteFooter, SUPPORT_EMAIL } from '../components/SiteFooter'

const UPDATED = '18 October 2026'

function LegalShell({ title, children }: { title: string; children: ReactNode }) {
  const { user } = useAuth()
  return (
    <div className="legal-page">
      <header className="landing-nav">
        <Link to="/" className="brand" aria-label="Épreuve home">
          <Logo />
        </Link>
        <nav className="landing-nav-actions" aria-label="Account">
          {user ? (
            <Link to="/dashboard" className="btn btn-sm">
              Dashboard
            </Link>
          ) : (
            <Link to="/login" className="btn btn-ghost btn-sm">
              Log in
            </Link>
          )}
        </nav>
      </header>
      <main className="legal">
        <h1>{title}</h1>
        <p className="muted small">Last updated {UPDATED}</p>
        {children}
      </main>
      <SiteFooter />
    </div>
  )
}

const Mail = () => <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>

export function TermsPage() {
  return (
    <LegalShell title="Terms of use">
      <p>
        These terms apply to everyone who uses Épreuve ("we", "the platform"). By creating an account you agree to them.
      </p>
      <h2>Your account</h2>
      <p>
        Give your real name: it appears on any certificate you earn. Keep your password private; you are responsible for
        what happens under your account. One person, one account.
      </p>
      <h2>Fair use</h2>
      <p>
        Practice attempts are limited per day so the service stays available to everyone. Don't try to work around the
        limits, scrape the question bank, share questions publicly, or interfere with the service or other users.
      </p>
      <h2>Certification and integrity</h2>
      <p>
        Certification attempts are proctored in your browser: we record when you leave the test tab, exit full screen,
        use more than one screen, or copy and paste. We don't use your camera or microphone. Attempts with integrity
        flags may be reviewed by a person before a certificate is issued. We may refuse or revoke a certificate if we
        find it was not earned honestly; a revoked certificate shows as revoked to anyone who checks it.
      </p>
      <h2>Fees</h2>
      <p>
        Practice and certification attempts are free. Claiming a certificate you have earned costs a one-time fee shown
        before you pay, processed by Paystack. See the <Link to="/refunds">refund policy</Link>.
      </p>
      <h2>Feedback and scores</h2>
      <p>
        Written and coding answers are graded and explained with the help of AI. We work to make grading accurate and
        fair, but feedback is guidance, not professional or career advice. If you think a score is wrong, contact us.
      </p>
      <h2>Company assessments</h2>
      <p>
        If a company invites you to an assessment, your results for that assessment are shared with that company and are
        not shown to you.
      </p>
      <h2>Availability and liability</h2>
      <p>
        We provide the service as it is and may change or pause features. To the extent the law allows, we are not
        liable for indirect losses, and our total liability is limited to the fees you paid us in the previous twelve
        months.
      </p>
      <h2>Ending your account</h2>
      <p>
        You can ask us to delete your account at any time. We may suspend accounts that break these terms.
      </p>
      <h2>Changes and law</h2>
      <p>
        We will post changes to these terms here. These terms are governed by the laws of the Federal Republic of
        Nigeria. Questions: <Mail />.
      </p>
    </LegalShell>
  )
}

export function PrivacyPage() {
  return (
    <LegalShell title="Privacy policy">
      <p>This explains what Épreuve collects, why, and who else handles it.</p>
      <h2>What we collect</h2>
      <ul>
        <li>Your name, email address and a securely hashed password.</li>
        <li>Your answers, scores, timings and the feedback generated for them.</li>
        <li>
          On certification and company assessments: integrity events such as leaving the test tab, exiting full screen,
          using more than one screen, or copy and paste. No camera, microphone or screen recording.
        </li>
        <li>Payment records: a reference, amount and status. Card and bank details go to Paystack, never to us.</li>
      </ul>
      <h2>Why</h2>
      <p>
        To run your tests, grade them, give feedback, issue and verify certificates, prevent cheating and abuse, send
        account emails (like password resets) and keep the service secure.
      </p>
      <h2>Who else handles it</h2>
      <ul>
        <li>AI providers (Google Gemini, OpenRouter) receive your written and coding answers to grade them and write feedback. They don't receive your name or email.</li>
        <li>Resend sends our emails. Paystack processes payments.</li>
        <li>Our hosting and database providers store the data.</li>
        <li>A company that invited you sees your results for that assessment.</li>
      </ul>
      <p>We don't sell your data or use it for advertising.</p>
      <h2>Certificates are public by link</h2>
      <p>
        Anyone with a certificate's code or link can see the holder's name, the test, the level, the score and the date.
        Codes are random, so certificates aren't listed or searchable.
      </p>
      <h2>Cookies</h2>
      <p>We use one essential cookie to keep you signed in. No tracking or advertising cookies.</p>
      <h2>Keeping and deleting data</h2>
      <p>
        We keep your data while your account exists. Ask us to delete it and we will, except payment records we must keep
        by law and the fact that a certificate code existed (so it can show as no longer valid). Email <Mail /> to access,
        correct or delete your data.
      </p>
    </LegalShell>
  )
}

export function RefundsPage() {
  return (
    <LegalShell title="Refund policy">
      <p>
        The certificate fee pays for issuing a digital certificate you have already earned, with a public verification
        link. It is issued as soon as the payment is confirmed.
      </p>
      <h2>When we refund</h2>
      <ul>
        <li>You were charged more than once for the same certificate.</li>
        <li>You paid but the certificate wasn't issued within 24 hours and we can't fix it.</li>
        <li>A payment went through because of an error on our side.</li>
      </ul>
      <h2>When we don't</h2>
      <ul>
        <li>The certificate was issued as described.</li>
        <li>The certificate was revoked because the attempt broke the integrity rules in the <Link to="/terms">terms</Link>.</li>
      </ul>
      <h2>How to ask</h2>
      <p>
        Email <Mail /> within 30 days of paying, with your account email and the payment reference from your Paystack
        receipt. Approved refunds go back to the original payment method through Paystack, usually within 5 to 10
        working days.
      </p>
    </LegalShell>
  )
}

export function ContactPage() {
  return (
    <LegalShell title="Contact">
      <p>
        For help with your account, a score you think is wrong, a payment, a certificate, or using Épreuve for your
        company's hiring, email <Mail />. We usually reply within two working days.
      </p>
      <p>
        To check a certificate someone shared with you, use <Link to="/verify">certificate verification</Link>.
      </p>
    </LegalShell>
  )
}
