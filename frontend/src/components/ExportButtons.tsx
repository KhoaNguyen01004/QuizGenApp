'use client';

import { Button } from '@/components/ui/button';
import { Download, FileText } from 'lucide-react';

interface ExportButtonsProps {
  markdown: string;
}

export function ExportButtons({ markdown }: ExportButtonsProps) {
  const downloadMarkdown = () => {
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'quiz.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadPDF = () => {
    window.print();
  };

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={downloadMarkdown}>
        <Download className="h-4 w-4 mr-2" />
        Markdown
      </Button>
      <Button size="sm" onClick={downloadPDF}>
        <FileText className="h-4 w-4 mr-2" />
        PDF
      </Button>
    </div>
  );
}
