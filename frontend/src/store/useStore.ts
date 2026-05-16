import { create } from 'zustand';
import { JobState } from '../types';

interface StoreState extends JobState {
  setJobId: (id: string) => void;
  updateStatus: (stage: string, progress: number, logs: string[]) => void;
  setResult: (markdown: string) => void;
  setError: (error: string) => void;
  reset: () => void;
}

const initialState: JobState = {
  jobId: null,
  stage: '',
  progress: 0,
  logs: [],
  markdown: null,
  isProcessing: false,
  error: null,
};

export const useStore = create<StoreState>((set) => ({
  ...initialState,
  
  setJobId: (id) => set({ jobId: id, isProcessing: true, error: null }),
  
  updateStatus: (stage, progress, logs) => set({ stage, progress, logs }),
  
  setResult: (markdown) => set({ markdown, isProcessing: false, progress: 100 }),
  
  setError: (error) => set({ error, isProcessing: false }),
  
  reset: () => set(initialState),
}));
