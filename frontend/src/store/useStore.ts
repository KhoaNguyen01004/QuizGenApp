import { create } from 'zustand';
import { JobState, QuizQuestion } from '../types';

interface StoreState extends JobState {
  setJobId: (id: string) => void;
  setIsProcessing: (isProcessing: boolean) => void;
  updateStatus: (stage: string, progress: number, logs: string[]) => void;
  setResult: (markdown: string, quiz?: QuizQuestion[]) => void;
  setError: (error: string) => void;
  reset: () => void;
}

const initialState: JobState = {
  jobId: null,
  stage: '',
  progress: 0,
  logs: [],
  markdown: null,
  quiz: null,
  isProcessing: false,
  error: null,
};

export const useStore = create<StoreState>((set) => ({
  ...initialState,
  
  setJobId: (id) => set({ jobId: id, isProcessing: true, error: null }),
  
  setIsProcessing: (isProcessing) => set({ isProcessing, error: null }),
  
  updateStatus: (stage, progress, logs) => set({ stage, progress, logs }),
  
  setResult: (markdown, quiz) => set({ markdown, quiz, isProcessing: false, progress: 100 }),
  
  setError: (error) => set({ error, isProcessing: false }),
  
  reset: () => set(initialState),
}));
