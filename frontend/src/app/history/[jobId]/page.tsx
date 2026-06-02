'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { use } from 'react';
import { ArrowLeft, CalendarDays, FileText, Hash } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { Header } from '@/components/Header';
import { QuizViewer } from '@/components/QuizViewer';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/services/api';
import { HistoryDetail } from '@/types';

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'long',
      timeStyle: 'short',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex justify-between py-2 border-b last:border-0 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

export default function HistoryDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const [entry, setEntry] = useState<HistoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getHistoryEntry(jobId)
      .then(setEntry)
      .catch(() => setError('Could not load this quiz. It may have been deleted.'))
      .finally(() => setLoading(false));
  }, [jobId]);

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden">
        <Header />

        <div className="flex-1 overflow-auto p-6 md:p-8">
          <div className="max-w-5xl mx-auto space-y-6">
            {/* Back navigation */}
            <Button
              variant="ghost"
              size="sm"
              className="-ml-2"
              render={<Link href="/history" />}
              nativeButton={false}
            >
              <ArrowLeft className="h-4 w-4 mr-1.5" />
              Back to History
            </Button>

            {/* Loading skeleton */}
            {loading && (
              <div className="space-y-4 animate-pulse">
                <div className="h-6 w-1/3 rounded bg-muted" />
                <div className="h-4 w-1/4 rounded bg-muted" />
                <div className="h-96 rounded-xl bg-muted" />
              </div>
            )}

            {/* Error state */}
            {error && (
              <div className="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-lg text-sm">
                <strong>Error:</strong> {error}
              </div>
            )}

            {/* Loaded content */}
            {entry && (
              <>
                {/* Page header */}
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
                    <h2
                      className="text-xl font-bold tracking-tight truncate"
                      title={entry.pdf_filename}
                    >
                      {entry.pdf_filename}
                    </h2>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <CalendarDays className="h-4 w-4" />
                      {formatDate(entry.created_at)}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Hash className="h-4 w-4" />
                      {entry.num_questions} questions
                    </span>
                    <Badge variant="secondary" className="capitalize">
                      {entry.mode}
                    </Badge>
                  </div>
                </div>

                {/* Tabs: Retake / Info */}
                <Tabs defaultValue="retake">
                  <TabsList>
                    <TabsTrigger value="retake">Retake Quiz</TabsTrigger>
                    <TabsTrigger value="info">Quiz Info</TabsTrigger>
                  </TabsList>

                  <TabsContent value="retake">
                    <div className="h-[calc(100vh-18rem)]">
                      <QuizViewer
                        markdown={entry.markdown}
                        quiz={entry.quiz}
                      />
                    </div>
                  </TabsContent>

                  <TabsContent value="info">
                    <div className="mt-4 space-y-6">
                      <Card>
                        <CardContent className="p-5 space-y-1">
                          <h3 className="text-sm font-semibold mb-3">Generation Details</h3>
                          <MetricRow label="PDF File" value={entry.pdf_filename} />
                          <MetricRow label="Generated On" value={formatDate(entry.created_at)} />
                          <MetricRow label="Mode" value={entry.mode} />
                          <MetricRow
                            label="Questions Requested"
                            value={entry.num_questions_requested}
                          />
                          <MetricRow label="Questions Generated" value={entry.num_questions} />
                        </CardContent>
                      </Card>

                      {entry.metrics && (
                        <Card>
                          <CardContent className="p-5 space-y-1">
                            <h3 className="text-sm font-semibold mb-3">Pipeline Metrics</h3>
                            <MetricRow
                              label="Total Time"
                              value={`${entry.metrics.total_time.toFixed(1)}s`}
                            />
                            <MetricRow
                              label="Candidates Generated"
                              value={entry.metrics.candidates_generated}
                            />
                            <MetricRow
                              label="Questions Accepted"
                              value={entry.metrics.questions_accepted}
                            />
                            <MetricRow
                              label="Questions Rejected"
                              value={entry.metrics.questions_rejected}
                            />
                            <MetricRow
                              label="Acceptance Rate"
                              value={`${Math.round(entry.metrics.acceptance_rate * 100)}%`}
                            />
                            <MetricRow
                              label="Avg Adversary Score"
                              value={entry.metrics.average_adversary_score.toFixed(1)}
                            />
                            <MetricRow
                              label="Est. Tokens Used"
                              value={entry.metrics.estimated_tokens_total.toLocaleString()}
                            />
                          </CardContent>
                        </Card>
                      )}
                    </div>
                  </TabsContent>
                </Tabs>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
