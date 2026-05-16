export interface GenerateResponse {
  job_id: string;
}

export interface StatusResponse {
  stage: string;
  progress: number;
  logs: string[];
}

export interface ResultResponse {
  markdown: string;
}

export type QuizMode = "accuracy" | "fast";

export interface JobState {
  jobId: string | null;
  stage: string;
  progress: number;
  logs: string[];
  markdown: string | null;
  isProcessing: boolean;
  error: string | null;
}
