'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card } from '@/components/ui/card';
import { FileText } from 'lucide-react';
import { ExportButtons } from '@/components/ExportButtons';

interface QuizViewerProps {
  markdown: string;
}

export function QuizViewer({ markdown }: QuizViewerProps) {
  return (
    <Card className="flex flex-col h-full overflow-hidden print:border-none print:shadow-none print:overflow-visible print:block">
      <div className="flex items-center justify-between p-4 border-b bg-muted/20 print:hidden">
        <h3 className="font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Generated Quiz
        </h3>
        <ExportButtons markdown={markdown} />
      </div>
      
      <div className="flex-1 overflow-auto p-6 md:p-8 bg-background print:bg-white print:p-0 print:block print:overflow-visible">
        <div className="prose prose-slate dark:prose-invert max-w-none print:!prose-slate print:max-w-full">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {markdown}
          </ReactMarkdown>
        </div>
      </div>
    </Card>
  );
}
