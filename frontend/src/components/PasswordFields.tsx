import { useState } from 'react'

export const MIN_PASSWORD = 8

/** The reason a new password can't be submitted yet, or null if it's fine. */
// eslint-disable-next-line react-refresh/only-export-components
export function newPasswordProblem(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD) return `Your password needs at least ${MIN_PASSWORD} characters.`
  if (password !== confirm) return "The two passwords don't match."
  return null
}

interface Props {
  password: string
  confirm: string
  onPassword: (v: string) => void
  onConfirm: (v: string) => void
  label?: string
}

/** "New password" + "Confirm password", sharing one show/hide toggle. */
export function NewPasswordFields({ password, confirm, onPassword, onConfirm, label = 'Password' }: Props) {
  const [show, setShow] = useState(false)
  const mismatch = confirm.length > 0 && confirm !== password
  const type = show ? 'text' : 'password'

  return (
    <>
      <div className="field">
        <label htmlFor="new-password">{label}</label>
        <div className="password-row">
          <input
            id="new-password"
            name="new-password"
            type={type}
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            maxLength={128}
            aria-describedby="password-hint"
            value={password}
            onChange={(e) => onPassword(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setShow((v) => !v)}
            aria-pressed={show}
            aria-controls="new-password confirm-password"
          >
            {show ? 'Hide' : 'Show'}
          </button>
        </div>
        <p id="password-hint" className="hint">
          At least {MIN_PASSWORD} characters.
        </p>
      </div>
      <div className="field">
        <label htmlFor="confirm-password">Confirm password</label>
        <input
          id="confirm-password"
          name="confirm-password"
          type={type}
          autoComplete="new-password"
          required
          maxLength={128}
          aria-invalid={mismatch}
          aria-describedby="confirm-status"
          value={confirm}
          onChange={(e) => onConfirm(e.target.value)}
        />
        <p id="confirm-status" className={`hint ${mismatch ? 'hint-error' : ''}`} aria-live="polite">
          {mismatch ? "Passwords don't match yet." : confirm && confirm === password ? 'Passwords match.' : ''}
        </p>
      </div>
    </>
  )
}
