'use client';

import { useEffect } from 'react';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import { HistoryCard } from '@/components/HistoryCard';
import { EmptyHistory } from '@/components/EmptyHistory';
import { useHistoryStore } from '@/store/useHistoryStore';
import { api } from '@/services/api';
import { toast } from 'sonner';

function SkeletonCard() {
  return (
    <div className="border rounded-xl p-5 space-y-3 animate-pulse bg-card">
      <div className="h-4 w-2/3 rounded bg-muted" />
      <div className="h-3 w-1/2 rounded bg-muted" />
      <div className="flex gap-2">
        <div className="h-5 w-16 rounded-full bg-muted" />
        <div className="h-5 w-20 rounded-full bg-muted" />
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const { entries, loading, error, fetchHistory, removeEntry } = useHistoryStore();

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleDelete = async (jobId: string) => {
    try {
      await api.deleteHistoryEntry(jobId);
      removeEntry(jobId);
      toast.success('History entry deleted.');
    } catch {
      toast.error('Failed to delete history entry.');
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <div className="flex-1 overflow-auto p-6 md:p-8">
          <div className="max-w-3xl mx-auto space-y-6">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">History</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Previously generated quizzes. Click Retake to attempt a quiz again.
              </p>
            </div>

            {error && (
              <div className="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-lg text-sm">
                <strong>Error:</strong> {error}
              </div>
            )}

            {loading && (
              <div className="space-y-4">
                {Array.from({ length: 3 }).map((_, i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {!loading && !error && entries.length === 0 && <EmptyHistory />}

            {!loading && entries.length > 0 && (
              <div className="space-y-4">
                {entries.map((entry) => (
                  <HistoryCard
                    key={entry.job_id}
                    entry={entry}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
