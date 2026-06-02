'use client';

import { useState } from 'react';
import Link from 'next/link';
import { CalendarDays, FileText, Hash, RotateCcw, Trash2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { HistoryEntry } from '@/types';

interface HistoryCardProps {
  entry: HistoryEntry;
  onDelete: (jobId: string) => Promise<void>;
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function truncateFilename(name: string, max = 40): string {
  if (name.length <= max) return name;
  const ext = name.lastIndexOf('.');
  if (ext > 0) {
    const base = name.slice(0, ext);
    const extension = name.slice(ext);
    return base.slice(0, max - extension.length - 3) + '...' + extension;
  }
  return name.slice(0, max - 3) + '...';
}

export function HistoryCard({ entry, onDelete }: HistoryCardProps) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleConfirmDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(entry.job_id);
    } finally {
      setDeleting(false);
      setOpen(false);
    }
  };

  const acceptanceRate = entry.metrics?.acceptance_rate;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          {/* Left: metadata */}
          <div className="flex-1 min-w-0 space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium truncate">
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate" title={entry.pdf_filename}>
                {truncateFilename(entry.pdf_filename)}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <CalendarDays className="h-3.5 w-3.5" />
                {formatDate(entry.created_at)}
              </span>
              <span className="flex items-center gap-1">
                <Hash className="h-3.5 w-3.5" />
                {entry.num_questions} questions
              </span>
            </div>

            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary" className="text-xs capitalize">
                {entry.mode}
              </Badge>
              {acceptanceRate !== undefined && acceptanceRate !== null && (
                <Badge
                  variant="outline"
                  className="text-xs"
                >
                  {Math.round(acceptanceRate * 100)}% accepted
                </Badge>
              )}
            </div>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              variant="outline"
              render={<Link href={`/history/${entry.job_id}`} />}
              nativeButton={false}
            >
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
              Retake
            </Button>

            <Dialog open={open} onOpenChange={setOpen}>
              <DialogTrigger
                render={
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  />
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span className="sr-only">Delete</span>
              </DialogTrigger>

              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete history entry?</DialogTitle>
                  <DialogDescription>
                    This will permanently remove the quiz generated from{' '}
                    <strong>{truncateFilename(entry.pdf_filename)}</strong>. This
                    action cannot be undone.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setOpen(false)}
                    disabled={deleting}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleConfirmDelete}
                    disabled={deleting}
                  >
                    {deleting ? 'Deleting…' : 'Delete'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
