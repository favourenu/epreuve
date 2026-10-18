import { api } from '../../api'
import type { AttemptListItem, AttemptMode, AttemptReview, Certificate, CertificateStatus, Quota } from '../../types'

export type Risk = 'none' | 'low' | 'high'
export type ReviewAction = 'approve' | 'reject' | 'revoke' | 'reinstate' | 'waive'

export interface AdminUser {
  id: string
  name: string
  email: string
  role: 'user' | 'admin'
  disabled: boolean
  created_at: string
  /** null = platform default, -1 = unlimited, otherwise practice attempts per 24 hours. */
  attempt_limit: number | null
  /** What applies now; null = unlimited. */
  effective_limit: number | null
}

export interface AdminUserRow extends AdminUser {
  attempts_completed: number
  average_percent: number | null
  certificates: number
  last_active: string | null
}

export interface AdminAttemptRow extends AttemptListItem {
  user: { id: string; name: string; email: string }
  risk: Risk | null
}

export interface IntegritySummary {
  risk: Risk
  counts: Record<string, number>
  seconds_away: number
  reasons: string[]
}

export interface AdminAttemptDetail {
  attempt: AdminAttemptRow
  review: AttemptReview | null
  progress: { position: number; total: number }
  integrity: IntegritySummary | null
  events: { kind: string; label: string; occurred_at: string; duration_ms: number | null; detail: string | null }[]
  invite: { company: string; email: string } | null
}

export interface Overview {
  users_total: number
  users_new_7d: number
  users_active_7d: number
  attempts_total: number
  attempts_completed_7d: number
  attempts_in_progress: number
  certificates_issued: number
  certificates_pending_review: number
  certificates_awaiting_payment: number
  revenue_kobo: number
  payments: number
  invites_open: number
  daily: { date: string; started: number; completed: number }[]
  by_test: { test_id: string; title: string; attempts: number; average_percent: number }[]
}

export interface LeaderRow {
  rank: number
  user: { id: string; name: string; email: string }
  score: number
  tests_taken: number
  attempts: number
}

export interface AdminCertificate extends Certificate {
  user: { id: string; name: string; email: string }
  integrity: IntegritySummary
}

export interface InviteRow {
  id: string
  email: string
  candidate_name: string
  company: string
  test_id: string
  test_title: string
  message: string | null
  created_at: string
  expires_at: string
  status: 'sent' | 'opened' | 'in_progress' | 'completed' | 'expired' | 'cancelled'
  attempt_id: string | null
  percent: number | null
  submitted_at: string | null
  risk: Risk | null
  link?: string
}

const get = <T,>(path: string) => api.raw<T>(`/api/admin${path}`)
const send = <T,>(method: string, path: string, body?: unknown) =>
  api.raw<T>(`/api/admin${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) })

const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') s.set(k, String(v))
  const str = s.toString()
  return str ? `?${str}` : ''
}

export const adminApi = {
  overview: () => get<Overview>('/overview'),
  users: (q: string, limit: number, offset: number) =>
    get<{ total: number; users: AdminUserRow[] }>(`/users${qs({ q, limit, offset })}`),
  user: (id: string) =>
    get<{ user: AdminUser; quota: Quota; attempts: AdminAttemptRow[]; certificates: Certificate[] }>(`/users/${id}`),
  updateUser: (id: string, patch: { role?: 'user' | 'admin'; disabled?: boolean; attempt_limit?: number | null }) =>
    send<AdminUser>('PATCH', `/users/${id}`, patch),
  attempts: (f: { mode?: AttemptMode | ''; status?: string; risk?: 'high' | ''; test_id?: string; limit: number; offset: number }) =>
    get<{ total: number; attempts: AdminAttemptRow[] }>(`/attempts${qs(f)}`),
  attempt: (id: string) => get<AdminAttemptDetail>(`/attempts/${id}`),
  leaderboard: (f: { test_id?: string; period: string; mode: string }) => get<LeaderRow[]>(`/leaderboard${qs(f)}`),
  certificates: (status?: CertificateStatus | '') => get<AdminCertificate[]>(`/certificates${qs({ status })}`),
  reviewCertificate: (id: string, action: ReviewAction, note?: string) =>
    send<Certificate>('POST', `/certificates/${id}/review`, { action, note }),
  invites: (company?: string) => get<InviteRow[]>(`/invites${qs({ company })}`),
  createInvite: (body: {
    email: string
    candidate_name: string
    company: string
    test_id: string
    message?: string
    valid_days?: number
  }) => send<InviteRow>('POST', '/invites', body),
  cancelInvite: (id: string) => send<InviteRow>('POST', `/invites/${id}/cancel`),
  invitesCsvUrl: (company?: string) => `/api/admin/invites.csv${qs({ company })}`,
}
