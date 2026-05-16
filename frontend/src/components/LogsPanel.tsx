'use client';

import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Terminal } from 'lucide-react';

interface LogsPanelProps {
  logs: string[];
}

export function LogsPanel({ logs }: LogsPanelProps) {
  return (
    <Card className="h-full flex flex-col bg-slate-950 text-slate-50 border-slate-800">
      <CardHeader className="py-3 px-4 border-b border-slate-800 bg-slate-900/50">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Terminal className="h-4 w-4" />
          Execution Logs
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 flex-1 overflow-hidden">
        <ScrollArea className="h-[300px] p-4 font-mono text-xs">
          {logs.length === 0 ? (
            <div className="text-slate-500 italic">Waiting for process to start...</div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, i) => (
                <div key={i} className={`${log.includes('[ERROR]') ? 'text-red-400' : log.includes('[WARN]') ? 'text-yellow-400' : 'text-slate-300'}`}>
                  {log}
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
