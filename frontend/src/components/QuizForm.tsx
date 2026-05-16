'use client';

import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { QuizMode } from '@/types';
import { Zap, Target } from 'lucide-react';

interface QuizFormProps {
  onGenerate: (mode: QuizMode, numQuestions: number) => void;
  disabled?: boolean;
}

export function QuizForm({ onGenerate, disabled }: QuizFormProps) {
  const [mode, setMode] = useState<QuizMode>('accuracy');
  const [numQs, setNumQs] = useState<string>('20');

  const handleGenerate = () => {
    const num = parseInt(numQs, 10);
    if (isNaN(num) || num < 1) return;
    onGenerate(mode, num);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quiz Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <label className="text-sm font-medium">Generation Mode</label>
          <div className="grid grid-cols-2 gap-4">
            <div 
              className={`border rounded-lg p-4 cursor-pointer flex flex-col items-center gap-2 transition-all ${mode === 'accuracy' ? 'border-primary ring-2 ring-primary/20 bg-primary/5' : 'hover:border-primary/50'}`}
              onClick={() => setMode('accuracy')}
            >
              <Target className={`h-6 w-6 ${mode === 'accuracy' ? 'text-primary' : 'text-muted-foreground'}`} />
              <div className="text-center">
                <p className="font-medium">Accuracy</p>
                <p className="text-xs text-muted-foreground">High quality, slower</p>
              </div>
            </div>
            <div 
              className={`border rounded-lg p-4 cursor-pointer flex flex-col items-center gap-2 transition-all ${mode === 'fast' ? 'border-primary ring-2 ring-primary/20 bg-primary/5' : 'hover:border-primary/50'}`}
              onClick={() => setMode('fast')}
            >
              <Zap className={`h-6 w-6 ${mode === 'fast' ? 'text-primary' : 'text-muted-foreground'}`} />
              <div className="text-center">
                <p className="font-medium">Fast</p>
                <p className="text-xs text-muted-foreground">Lower quality, rapid</p>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <label className="text-sm font-medium" htmlFor="numQs">Number of Questions</label>
          <Input 
            id="numQs"
            type="number" 
            min="1" 
            max="100"
            value={numQs} 
            onChange={(e) => setNumQs(e.target.value)} 
          />
        </div>
      </CardContent>
      <CardFooter>
        <Button 
          className="w-full" 
          size="lg" 
          onClick={handleGenerate}
          disabled={disabled || !numQs}
        >
          Generate Quiz
        </Button>
      </CardFooter>
    </Card>
  );
}
