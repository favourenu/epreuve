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
}

export interface AttemptState {
  id: string
  test_id: string
  test_title: string
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
