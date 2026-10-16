const CATEGORY_LABELS: Record<string, string> = {
  numerical_reasoning: 'Numerical reasoning',
  critical_thinking: 'Critical thinking',
  attention_to_detail: 'Attention to detail',
  software_engineering: 'Software engineering',
  python: 'Python',
  ai_fundamentals: 'AI & ML',
  coding: 'Coding',
  situational_judgement: 'Situational judgement',
  communication: 'Written communication',
}

/** The practice test that drills each category, for "practise next" suggestions. */
export const CATEGORY_TEST: Record<string, string> = {
  numerical_reasoning: 'numerical-reasoning',
  critical_thinking: 'critical-thinking',
  attention_to_detail: 'attention-to-detail',
  software_engineering: 'software-engineering',
  python: 'python-knowledge',
  ai_fundamentals: 'ai-fundamentals',
  coding: 'python-coding',
  situational_judgement: 'situational-judgement',
  communication: 'written-communication',
}

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = h ? String(m).padStart(2, '0') : String(m)
  return `${h ? `${h}:` : ''}${mm}:${String(sec).padStart(2, '0')}`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function scoreTone(percent: number | null | undefined): 'good' | 'ok' | 'bad' | 'none' {
  if (percent == null) return 'none'
  if (percent >= 75) return 'good'
  if (percent >= 50) return 'ok'
  return 'bad'
}

export function formatValue(value: unknown): string {
  if (typeof value === 'string' && value.endsWith('...(truncated)')) return value
  return JSON.stringify(value)
}

export function wordCount(text: string): number {
  const t = text.trim()
  return t ? t.split(/\s+/).length : 0
}

/** localStorage helpers: storage can be unavailable (private mode), so never throw. */
export const draftStore = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key: string, value: string) {
    try {
      localStorage.setItem(key, value)
    } catch {
      /* ignore */
    }
  },
  remove(key: string) {
    try {
      localStorage.removeItem(key)
    } catch {
      /* ignore */
    }
  },
}
