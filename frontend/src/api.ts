import type {
  AIStatus,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running on port 8000?')
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  tests: () => request<TestSummary[]>('/api/tests'),
  test: (id: string) => request<TestSummary>(`/api/tests/${encodeURIComponent(id)}`),
  stats: () => request<Stats>('/api/stats'),
  aiStatus: () => request<AIStatus>('/api/ai/status'),
  attempts: (status?: string) =>
    request<AttemptListItem[]>(`/api/attempts?limit=200${status ? `&status=${status}` : ''}`),
  start: (testId: string) => post<AttemptState>('/api/attempts', { test_id: testId }),
  attempt: (id: string) => request<AttemptState>(`/api/attempts/${id}`),
  answer: (id: string, position: number, answer: unknown) =>
    post<AttemptState>(`/api/attempts/${id}/answer`, { position, answer }),
  run: (id: string, position: number, code: string) =>
    post<RunResult>(`/api/attempts/${id}/run`, { position, code }),
  finish: (id: string) => post<AttemptState>(`/api/attempts/${id}/finish`),
  review: (id: string) => request<AttemptReview>(`/api/attempts/${id}/review`),
  retryFeedback: (id: string) => post<AttemptState>(`/api/attempts/${id}/feedback/retry`),
}
