export interface User {
  id: string
  email: string
  name: string
  role: 'user' | 'admin'
}

export type AttemptMode = 'practice' | 'certification' | 'invite'
export type CertificateStatus = 'issued' | 'under_review' | 'rejected' | 'revoked'

export interface Certificate {
  id: string
  code: string
  test_id: string
  test_title: string
  percent: number
  level: 'pass' | 'distinction'
  status: CertificateStatus
  attempt_id: string
  created_at: string
  issued_at: string | null
  review_note?: string | null
}

export interface PublicCertificate {
  code: string
  holder_name: string
  test_title: string
  level: 'pass' | 'distinction'
  percent: number
  issued_at: string | null
  valid: boolean
  proctored: boolean
}

export interface InviteView {
  company: string
  candidate_name: string
  email: string
  test_id: string
  test_title: string
  time_limit_minutes: number | null
  question_count: number | null
  message: string | null
  expires_at: string
  status: 'sent' | 'opened' | 'in_progress' | 'completed' | 'expired' | 'cancelled'
  attempt_id: string | null
}

export type IntegrityKind =
  | 'focus_lost'
  | 'fullscreen_exit'
  | 'multiple_screens'
  | 'paste'
  | 'copy'
  | 'context_menu'
  | 'reload'

export interface IntegrityEventIn {
  kind: IntegrityKind
  duration_ms?: number
  detail?: string
}

export type QuestionType = 'mcq' | 'code' | 'written'

export interface CodeExample {
  args: unknown[]
  expected: unknown
}

/** A question as served during a test: no answers. */
export interface PublicQuestion {
  id: string
  type: QuestionType
  category: string
  topic: string
  difficulty: 'easy' | 'medium' | 'hard'
  prompt: string
  points: number
  options?: string[]
  language?: string
  function_name?: string
  starter_code?: string
  examples?: CodeExample[]
  hidden_test_count?: number
  min_words?: number
  max_words?: number
}

/** The full question, available in the review after an attempt is completed. */
export interface FullQuestion extends PublicQuestion {
  answer?: number
  option_scores?: number[] | null
  explanation?: string
  reference_solution?: string
  rubric?: string[]
  model_answer?: string
}

export type FeedbackStatus = 'pending' | 'ready' | 'failed' | null

export interface TestSummary {
  id: string
  title: string
  description: string
  skill_area: string
  time_limit_minutes: number
  question_count: number
  instructions: string[]
  attempts: number
  best_percent: number | null
  last_percent: number | null
  certification_pass_percent: number
  certification_distinction_percent: number
  certification_cooldown_days: number
  certification_available_at: string | null
  certificate: Certificate | null
}

export interface AttemptState {
  id: string
  test_id: string
  test_title: string
  mode: AttemptMode
  proctored: boolean
  company: string | null
  status: 'in_progress' | 'completed'
  started_at: string
  deadline: string
  submitted_at: string | null
  timed_out: boolean
  server_time: string
  remaining_seconds: number
  position: number
  total_questions: number
  question: PublicQuestion | null
  score: number | null
  max_score: number | null
  percent: number | null
  feedback_status: FeedbackStatus
}

export interface AttemptListItem {
  id: string
  test_id: string
  test_title: string
  mode: AttemptMode
  company: string | null
  status: 'in_progress' | 'completed'
  started_at: string
  submitted_at: string | null
  timed_out: boolean
  score: number | null
  max_score: number | null
  percent: number | null
  feedback_status: FeedbackStatus
}

export interface TestOutcome {
  hidden: boolean
  passed: boolean
  args?: unknown
  expected?: unknown
  output?: unknown
  error?: string | null
  stdout?: string
}

export interface RunResult {
  error: string | null
  timed_out: boolean
  passed: number
  total: number
  tests: TestOutcome[]
}

export interface Grading {
  skipped?: boolean
  selected?: number | null
  correct?: number
  error?: string | null
  timed_out?: boolean
  passed?: number
  total?: number
  tests?: TestOutcome[]
  word_count?: number
  feedback?: string
}

export interface ReviewItem {
  position: number
  question: FullQuestion
  answer: number | { code: string } | { text: string } | null
  points: number | null
  max_points: number
  is_correct: boolean | null
  grading: Grading | null
  time_spent_seconds: number | null
}

export interface CategoryScore {
  category: string
  points: number
  max_points: number
  percent: number
  pending: boolean
}

export interface StudyItem {
  topic: string
  priority: 'high' | 'medium' | 'low'
  why: string
  how_to_practice: string
}

export interface FeedbackReport {
  summary: string
  strengths: string[]
  weaknesses: string[]
  study_plan: StudyItem[]
  test_taking_tips: string[]
}

export interface AttemptReview {
  attempt: AttemptListItem
  certificate: Certificate | null
  duration_seconds: number | null
  categories: CategoryScore[]
  items: ReviewItem[]
  feedback: FeedbackReport | null
  feedback_provider: string | null
  feedback_error: string | null
}

export interface CategoryStat {
  category: string
  questions: number
  points: number
  max_points: number
  percent: number
}

export interface Stats {
  completed_attempts: number
  average_percent: number | null
  categories: CategoryStat[]
  history: AttemptListItem[]
}

export interface AIStatus {
  providers: { name: string; model: string }[]
}
