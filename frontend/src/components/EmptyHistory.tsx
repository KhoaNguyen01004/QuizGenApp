import Link from 'next/link';
import { HistoryIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function EmptyHistory() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="p-4 rounded-full bg-muted">
        <HistoryIcon className="h-8 w-8 text-muted-foreground" />
      </div>
      <div className="space-y-1">
        <h3 className="text-lg font-semibold">No quizzes yet</h3>
        <p className="text-sm text-muted-foreground">
          Generated quizzes will appear here once you complete a generation.
        </p>
      </div>
      <Button render={<Link href="/" />} nativeButton={false}>Generate your first quiz</Button>
    </div>
  );
}
