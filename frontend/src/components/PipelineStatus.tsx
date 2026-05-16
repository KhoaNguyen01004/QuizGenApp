'use client';

import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';

interface PipelineStatusProps {
  stage: string;
  progress: number;
}

const STAGES = [
  'Extracting PDF',
  'Curating Knowledge',
  'Generating Questions',
  'Validating Questions',
  'Creating Explanations',
  'Complete'
];

export function PipelineStatus({ stage, progress }: PipelineStatusProps) {
  // Infer active step index based on the current stage string.
  // In a real app this might be more robust if backend sends an enum.
  let currentIndex = STAGES.findIndex(s => s.toLowerCase() === stage.toLowerCase());
  if (currentIndex === -1) currentIndex = 0;
  if (progress === 100) currentIndex = STAGES.length - 1;

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-medium">Generation Progress</h3>
            <p className="text-sm text-muted-foreground">{stage || 'Preparing...'}</p>
          </div>
          <div className="text-2xl font-bold">{progress}%</div>
        </div>
        
        <Progress value={progress} className="h-2 mb-8" />

        <div className="space-y-4">
          {STAGES.map((s, i) => {
            const isCompleted = i < currentIndex;
            const isActive = i === currentIndex && progress < 100;

            return (
              <div key={s} className="flex items-center gap-3">
                {isCompleted ? (
                   <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : isActive ? (
                   <Loader2 className="h-5 w-5 text-primary animate-spin" />
                ) : (
                   <Circle className="h-5 w-5 text-muted" />
                )}
                <span className={`${isCompleted ? 'text-foreground' : isActive ? 'font-medium text-primary' : 'text-muted-foreground'}`}>
                  {s}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
