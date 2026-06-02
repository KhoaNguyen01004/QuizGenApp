import { create } from 'zustand';
import { api } from '../services/api';
import { HistoryEntry } from '../types';

interface HistoryStoreState {
  entries: HistoryEntry[];
  loading: boolean;
  error: string | null;
  fetchHistory: () => Promise<void>;
  removeEntry: (jobId: string) => void;
}

export const useHistoryStore = create<HistoryStoreState>((set) => ({
  entries: [],
  loading: false,
  error: null,

  fetchHistory: async () => {
    set({ loading: true, error: null });
    try {
      const entries = await api.getHistory();
      set({ entries, loading: false });
    } catch {
      set({ error: 'Failed to load history.', loading: false });
    }
  },

  /** Optimistically remove an entry from local state after a successful delete. */
  removeEntry: (jobId: string) =>
    set((state) => ({
      entries: state.entries.filter((e) => e.job_id !== jobId),
    })),
}));
