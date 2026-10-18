import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { IntegrityEventIn } from '../types'

const RULES = [
  'I am using one screen. Extra monitors are disconnected.',
  "I've closed other tabs and apps, and turned off browser extensions (AI helpers, grammar or translation tools). A private/incognito window is the easiest way.",
  'I will stay in full screen, in this window, until I finish.',
  'I will work alone, without notes, websites, other people or AI tools.',
]

/** Pre-test checklist: every rule must be ticked before a proctored attempt starts. */
export function RulesModal({
  title,
  busy,
  error,
  onCancel,
  onAgree,
}: {
  title: string
  busy: boolean
  error?: string | null
  onCancel: () => void
  onAgree: () => void
}) {
  const [checked, setChecked] = useState<boolean[]>(RULES.map(() => false))
  const all = checked.every(Boolean)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onCancel()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onCancel])

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="rules-title">
      <div className="modal modal-wide">
        <p className="eyebrow">Proctored assessment</p>
        <h2 id="rules-title">{title}</h2>
        <p className="muted">
          During this assessment Épreuve records when you leave the test window, exit full screen, connect a second
          screen, or copy and paste. Attempts with serious issues are reviewed by a person before any result is
          confirmed. There is no camera or microphone recording.
        </p>
        <fieldset className="checklist">
          <legend className="visually-hidden">Confirm each rule</legend>
          {RULES.map((rule, i) => (
            <label key={rule} className="check">
              <input
                type="checkbox"
                checked={checked[i]}
                onChange={(e) => setChecked((c) => c.map((v, j) => (j === i ? e.target.checked : v)))}
              />
              <span>{rule}</span>
            </label>
          ))}
        </fieldset>
        {error && <div className="error-box" role="alert">{error}</div>}
        <div className="actions actions-end">
          <button className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            Not yet
          </button>
          <button className="btn btn-primary" onClick={onAgree} disabled={!all || busy}>
            {busy ? 'Starting...' : 'I agree, start now'}
          </button>
        </div>
        {!all && <p className="hint center">Tick every item to continue.</p>}
      </div>
    </div>
  )
}

type ScreenWithExtended = Screen & { isExtended?: boolean } & EventTarget

const fullscreenSupported = () => typeof document !== 'undefined' && !!document.fullscreenEnabled
const inFullscreen = () => !!document.fullscreenElement

/**
 * Watches a proctored attempt and reports integrity events to the server in batches.
 * Returns state the test screen uses to block the UI until the candidate is back in full screen.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useProctoring(attemptId: string | undefined, enabled: boolean) {
  const queue = useRef<IntegrityEventIn[]>([])
  const awaySince = useRef<number | null>(null)
  const [fullscreen, setFullscreen] = useState(() => !fullscreenSupported() || inFullscreen())
  const [notice, setNotice] = useState<string | null>(null)
  const [extraScreen, setExtraScreen] = useState(false)

  const record = useCallback((event: IntegrityEventIn, message?: string) => {
    queue.current.push(event)
    if (message) setNotice(message)
  }, [])

  const flush = useCallback(() => {
    if (!attemptId || queue.current.length === 0) return
    const batch = queue.current.splice(0, 50)
    api.reportIntegrity(attemptId, batch).catch(() => {
      // Keep events if the network blips; drop them if the attempt has ended (409).
      if (navigator.onLine) return
      queue.current.unshift(...batch)
    })
  }, [attemptId])

  useEffect(() => {
    if (!enabled || !attemptId) return

    // Reloading the test page mid-attempt is recorded (the first load isn't).
    const key = `epreuve:loaded:${attemptId}`
    try {
      if (sessionStorage.getItem(key)) record({ kind: 'reload' })
      sessionStorage.setItem(key, '1')
    } catch {
      /* storage unavailable */
    }

    const leave = () => {
      if (awaySince.current == null) awaySince.current = Date.now()
    }
    const back = () => {
      if (document.visibilityState !== 'visible' || !document.hasFocus() || awaySince.current == null) return
      const ms = Date.now() - awaySince.current
      awaySince.current = null
      if (ms >= 500) {
        record(
          { kind: 'focus_lost', duration_ms: ms },
          `You left the test window for ${Math.round(ms / 1000)} s. This has been recorded.`,
        )
      }
    }
    const onVisibility = () => (document.visibilityState === 'hidden' ? leave() : back())

    const onFullscreen = () => {
      const now = inFullscreen()
      setFullscreen(now || !fullscreenSupported())
      if (!now) record({ kind: 'fullscreen_exit' }, 'You exited full screen. This has been recorded.')
    }
    const block = (kind: 'paste' | 'copy' | 'context_menu', message: string) => (e: Event) => {
      e.preventDefault()
      record({ kind }, message)
    }
    const onPaste = block('paste', 'Pasting is disabled during proctored assessments. The attempt was recorded.')
    const onCopy = block('copy', 'Copying is disabled during proctored assessments.')
    const onCut = block('copy', 'Copying is disabled during proctored assessments.')
    const onContext = block('context_menu', 'The right-click menu is disabled during proctored assessments.')

    // Second screen detection (Chrome and Edge). Other browsers don't expose it.
    const screen = window.screen as ScreenWithExtended
    let lastExtended = false
    const checkScreens = () => {
      const extended = !!screen.isExtended
      setExtraScreen(extended)
      if (extended && !lastExtended) record({ kind: 'multiple_screens' }, 'A second screen is connected. Disconnect it to continue cleanly.')
      lastExtended = extended
    }
    checkScreens()

    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('blur', leave)
    window.addEventListener('focus', back)
    document.addEventListener('fullscreenchange', onFullscreen)
    document.addEventListener('paste', onPaste, true)
    document.addEventListener('copy', onCopy, true)
    document.addEventListener('cut', onCut, true)
    document.addEventListener('contextmenu', onContext, true)
    if ('addEventListener' in screen) screen.addEventListener('change', checkScreens)
    const timer = window.setInterval(flush, 3000)
    window.addEventListener('pagehide', flush)

    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('blur', leave)
      window.removeEventListener('focus', back)
      document.removeEventListener('fullscreenchange', onFullscreen)
      document.removeEventListener('paste', onPaste, true)
      document.removeEventListener('copy', onCopy, true)
      document.removeEventListener('cut', onCut, true)
      document.removeEventListener('contextmenu', onContext, true)
      if ('removeEventListener' in screen) screen.removeEventListener('change', checkScreens)
      window.clearInterval(timer)
      window.removeEventListener('pagehide', flush)
      flush()
    }
  }, [attemptId, enabled, record, flush])

  // Leave full screen when the attempt ends or the page is left.
  useEffect(() => {
    if (!enabled) return
    return () => {
      if (inFullscreen()) document.exitFullscreen().catch(() => {})
    }
  }, [enabled])

  const enterFullscreen = useCallback(async () => {
    if (!fullscreenSupported()) return setFullscreen(true)
    try {
      await document.documentElement.requestFullscreen({ navigationUI: 'hide' })
      setFullscreen(true)
    } catch {
      setNotice("Your browser didn't allow full screen. Try again, or use Chrome or Edge.")
    }
  }, [])

  return { fullscreen, enterFullscreen, notice, dismissNotice: () => setNotice(null), extraScreen, flush }
}

/** Blocks the test until the candidate is in full screen. The timer keeps running. */
export function FullscreenGate({ onEnter, first }: { onEnter: () => void; first: boolean }) {
  return (
    <div className="modal-backdrop gate" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <div className="modal">
        <h2 id="gate-title">{first ? 'Enter full screen to begin' : 'Return to full screen'}</h2>
        <p className="muted">
          {first
            ? 'This assessment runs in full screen. Your timer has started.'
            : 'You left full screen, and this was recorded. Return to full screen to keep going; your timer is still running.'}
        </p>
        <div className="actions actions-end">
          <button className="btn btn-primary btn-lg" onClick={onEnter} autoFocus>
            {first ? 'Enter full screen' : 'Return to full screen'}
          </button>
        </div>
      </div>
    </div>
  )
}
