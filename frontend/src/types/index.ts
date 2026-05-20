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
  quiz?: QuizQuestion[]; // Added to match "Backend đã trả về JSON quiz hoàn chỉnh"
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
  isProcessing: boolean;
  error: string | null;
}
