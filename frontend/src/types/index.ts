export interface GenerateResponse {
  job_id: string;
}

export interface StatusResponse {
  stage: string;
  progress: number;
  logs: string[];
}

// H-6: pipeline metrics returned by /result/{job_id}
export interface PipelineMetricsSummary {
  total_time: number;
  candidates_generated: number;
  questions_accepted: number;
  questions_rejected: number;
  acceptance_rate: number;
  average_adversary_score: number;
  estimated_tokens_total: number;
}

export interface ResultResponse {
  markdown: string;
  quiz?: QuizQuestion[];
  metrics?: PipelineMetricsSummary; // H-6: was missing, backend always returns this
}

export interface QuizQuestion {
  id: number;
  question: string;
  options: string[];
  correct_answer: number;
  explanation: string;
  difficulty?: string;
  topic?: string;
}

export type QuizMode = "accuracy" | "fast";

// ── History ────────────────────────────────────────────────────────────────

/** Metadata-only entry returned by GET /history (no quiz array or markdown). */
export interface HistoryEntry {
  job_id: string;
  pdf_filename: string;
  created_at: string; // ISO-8601 UTC
  mode: QuizMode;
  num_questions_requested: number;
  num_questions: number;
  metrics?: PipelineMetricsSummary | null;
}

/** Full entry returned by GET /history/{job_id} — includes quiz and markdown. */
export interface HistoryDetail extends HistoryEntry {
  quiz: QuizQuestion[];
  markdown: string;
}

export interface JobState {
  jobId: string | null;
  stage: string;
  progress: number;
  logs: string[];
  markdown: string | null;
  quiz?: QuizQuestion[] | null;
  metrics?: PipelineMetricsSummary | null; // H-6: store metrics in state
  isProcessing: boolean;
  error: string | null;
}
