import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'

const TEST_TYPES = [
  {
    name: 'Cognitive ability',
    detail: 'Numerical reasoning, critical thinking and attention to detail, under strict time limits.',
    tags: ['Numerical', 'Logic', 'Detail'],
  },
  {
    name: 'Technical knowledge',
    detail: 'Software engineering fundamentals, Python and the AI & ML concepts entry-level engineers are expected to know.',
    tags: ['Git & APIs', 'SQL', 'Python', 'LLMs'],
  },
  {
    name: 'Coding',
    detail: 'Timed Python problems in a real editor. Run the examples, then get scored on hidden edge cases.',
    tags: ['Hidden tests', 'Partial credit'],
  },
  {
    name: 'Soft skills',
    detail: 'Workplace judgement scenarios and written messages, graded against a hiring rubric.',
    tags: ['Situational judgement', 'Writing'],
  },
]

const STEPS = [
  { title: 'Take an assessment', body: 'Timed, one question at a time, no going back.' },
  { title: 'Get scored', body: 'Instant results by skill, with an explanation for every question.' },
  { title: 'Get a study plan', body: 'An AI coach reviews your answers and tells you exactly what to work on.' },
  { title: 'Get certified', body: 'Score highly under proctored conditions and earn a certificate employers can verify.' },
]

function QuestionPreview() {
  return (
    <div className="preview" aria-hidden="true">
      <div className="preview-bar">
        <span className="preview-title">Numerical Reasoning</span>
        <span className="preview-timer tabular">08:41</span>
      </div>
      <div className="preview-progress">
        <span style={{ width: '37%' }} />
      </div>
      <div className="preview-body">
        <p className="preview-q">
          <span className="preview-num">Q3</span>A laptop sells for $800 after a 20% discount. What was the original price?
        </p>
        <ul className="preview-options">
          <li><span>A</span>$960</li>
          <li className="is-selected"><span>B</span>$1,000</li>
          <li><span>C</span>$1,040</li>
        </ul>
      </div>
      <div className="preview-note">
        <strong>Study next</strong>
        Reverse percentages: divide by 0.8, don't add 20% back.
      </div>
    </div>
  )
}

export function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <Link to="/" className="brand" aria-label="Épreuve home">
          <Logo />
        </Link>
        <nav className="landing-nav-actions" aria-label="Account">
          <Link to="/login" className="btn btn-ghost">
            Log in
          </Link>
          <Link to="/signup" className="btn btn-primary">
            Get started
          </Link>
        </nav>
      </header>

      <main>
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">Job-readiness assessments and certification</p>
            <h1>
              Prove what you can do, <em>and show it.</em>
            </h1>
            <p className="lead">
              Épreuve assesses the cognitive, technical, coding and workplace skills employers hire for. Every attempt
              is timed and scored, an AI coach shows you what to work on, and high scores earn a certificate anyone
              can verify.
            </p>
            <div className="hero-actions">
              <Link to="/signup" className="btn btn-primary btn-lg">
                Get started, it's free
              </Link>
              <Link to="/login" className="btn btn-lg">
                Log in
              </Link>
            </div>
          </div>
          <QuestionPreview />
        </section>

        <section className="landing-section" aria-labelledby="types-title">
          <p className="eyebrow">What we assess</p>
          <h2 id="types-title">Four kinds of assessment, one platform</h2>
          <div className="type-grid">
            {TEST_TYPES.map((t, i) => (
              <article key={t.name} className="type-card">
                <span className="type-index">0{i + 1}</span>
                <h3>{t.name}</h3>
                <p>{t.detail}</p>
                <ul className="type-tags" aria-label={`${t.name} topics`}>
                  {t.tags.map((tag) => (
                    <li key={tag}>{tag}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" aria-labelledby="how-title">
          <p className="eyebrow">How it works</p>
          <h2 id="how-title">From first attempt to certified</h2>
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s.title}>
                <span className="step-num">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section realism" aria-labelledby="real-title">
          <div>
            <p className="eyebrow">Built for integrity</p>
            <h2 id="real-title">Scores you, and employers, can trust</h2>
          </div>
          <ul className="realism-list">
            <li>
              <strong>The clock is the server's, not your browser's.</strong> Close the tab and the timer keeps running.
            </li>
            <li>
              <strong>No going back.</strong> Once you move on, an answer is final.
            </li>
            <li>
              <strong>Hidden test cases</strong> decide your coding score, not just the examples you can see.
            </li>
            <li>
              <strong>Proctored certification.</strong> Full screen, tab-switch and second-screen detection, with every
              attempt's integrity report reviewed before a certificate is issued.
            </li>
            <li>
              <strong>Verifiable certificates.</strong> Each one has a public link employers can check.
            </li>
          </ul>
        </section>

        <section className="cta-band">
          <h2>Your skills, measured properly.</h2>
          <Link to="/signup" className="btn btn-primary btn-lg">
            Create your free account
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <Logo size={22} />
        <span className="muted small">
          <Link to="/verify">Verify a certificate</Link> · Épreuve is French for "test".
        </span>
      </footer>
    </div>
  )
}
