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
