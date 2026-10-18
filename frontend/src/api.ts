import type {
  AIStatus,
  Certificate,
  IntegrityEventIn,
  InviteView,
  PublicCertificate,
  Quota,
  User,
  AttemptListItem,
  AttemptReview,
  AttemptState,
  RunResult,
  Stats,
  TestSummary,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg: string }

/** Turn FastAPI's validation errors into one readable sentence. */
function formatValidation(issues: ValidationIssue[]): string {
  return issues
    .map((d) => {
      const field = d.loc?.[d.loc.length - 1]
      const msg = d.msg.replace(/^Value error, /, '')
      return typeof field === 'string' && field !== 'body' ? `${field[0].toUpperCase()}${field.slice(1)}: ${msg}` : msg
    })
    .join('. ')
}

let onUnauthorized: (() => void) | null = null

/** Called when any request fails with 401 (e.g. the session expired). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, "Can't reach the Épreuve server. Check that the backend is running, then try again.")
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = formatValidation(body.detail)
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && !path.startsWith('/api/auth/')) onUnauthorized?.()
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  /** Any JSON endpoint (used by the admin client). */
  raw: <T,>(path: string, init?: RequestInit) => request<T>(path, init),
  me: () => request<User>('/api/auth/me'),
  login: (email: string, password: string) => post<User>('/api/auth/login', { email, password }),
  signup: (name: string, email: string, password: string) =>
    post<User>('/api/auth/signup', { name, email, password }),
  logout: () => post<void>('/api/auth/logout'),
  forgotPassword: (email: string) => post<{ detail: string }>('/api/auth/password/forgot', { email }),
  checkResetToken: (token: string) => post<{ email: string }>('/api/auth/password/reset/check', { token }),
  resetPassword: (token: string, password: string) => post<User>('/api/auth/password/reset', { token, password }),
  tests: () => request<TestSummary[]>('/api/tests'),
  test: (id: string) => request<TestSummary>(`/api/tests/${encodeURIComponent(id)}`),
  stats: () => request<Stats>('/api/stats'),
  aiStatus: () => request<AIStatus>('/api/ai/status'),
  attempts: (status?: string) =>
    request<AttemptListItem[]>(`/api/attempts?limit=200${status ? `&status=${status}` : ''}`),
  start: (testId: string, mode: 'practice' | 'certification' = 'practice', agreeToRules = false) =>
    post<AttemptState>('/api/attempts', { test_id: testId, mode, agree_to_rules: agreeToRules }),
  reportIntegrity: (id: string, events: IntegrityEventIn[]) =>
    request<{ recorded: number }>(`/api/attempts/${id}/integrity`, {
      method: 'POST',
      body: JSON.stringify({ events }),
      keepalive: true, // still delivered if the page is closing
    }),
  certificates: () => request<Certificate[]>('/api/certificates'),
  quota: () => request<Quota>('/api/attempts/quota'),
  payForCertificate: (id: string) => post<{ authorization_url: string }>(`/api/certificates/${id}/pay`),
  verifyPayment: (reference: string) =>
    post<Certificate>(`/api/payments/${encodeURIComponent(reference)}/verify`),
  verifyCertificate: (code: string) => request<PublicCertificate>(`/api/public/certificates/${encodeURIComponent(code)}`),
  invite: (token: string) => request<InviteView>(`/api/invites/${encodeURIComponent(token)}`),
  startInvite: (token: string) =>
    post<AttemptState>(`/api/invites/${encodeURIComponent(token)}/start`, { agree_to_rules: true }),
  attempt: (id: string) => request<AttemptState>(`/api/attempts/${id}`),
  answer: (id: string, position: number, answer: unknown) =>
    post<AttemptState>(`/api/attempts/${id}/answer`, { position, answer }),
  run: (id: string, position: number, code: string) =>
    post<RunResult>(`/api/attempts/${id}/run`, { position, code }),
  finish: (id: string) => post<AttemptState>(`/api/attempts/${id}/finish`),
  review: (id: string) => request<AttemptReview>(`/api/attempts/${id}/review`),
  retryFeedback: (id: string) => post<AttemptState>(`/api/attempts/${id}/feedback/retry`),
}
