/** The Épreuve mark: an E on an ink tile, with the acute accent as a highlighter stroke. */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="logo-mark" focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--brand)" />
      <path d="M10 11h12v3h-8.6v2.6H20v3h-6.6V22H22v3H10z" fill="var(--brand-ink)" />
      <path d="M15.5 8.2 20.5 5" stroke="var(--mark)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo">
      <LogoMark size={size} />
      <span className="logo-word">Épreuve</span>
    </span>
  )
}
