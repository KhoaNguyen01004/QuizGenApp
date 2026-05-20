'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Card } from '@/components/ui/card';
import { FileText, CheckCircle2, XCircle } from 'lucide-react';
import { ExportButtons } from '@/components/ExportButtons';
import { QuizQuestion } from '@/types';

interface QuizViewerProps {
  markdown: string;
  quiz?: QuizQuestion[];
}

export function QuizViewer({ markdown, quiz }: QuizViewerProps) {
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const [expandedExplanations, setExpandedExplanations] = useState<Record<number, boolean>>({});

  const handleSelect = (questionId: number, optionIndex: number) => {
    if (submitted) return;
    setSelectedAnswers(prev => ({
      ...prev,
      [questionId]: optionIndex
    }));
  };

  const handleSubmit = () => {
    setSubmitted(true);
  };

  const toggleExplanation = (questionId: number) => {
    setExpandedExplanations(prev => ({
      ...prev,
      [questionId]: !prev[questionId]
    }));
  };

  const calculateCorrect = () => {
    if (!quiz) return 0;
    let count = 0;
    quiz.forEach(q => {
      if (selectedAnswers[q.id] === q.correct_answer) count++;
    });
    return count;
  };

  if (!quiz || quiz.length === 0) {
    // Fallback to purely markdown view
    return (
      <Card className="flex flex-col h-full overflow-hidden print:border-none print:shadow-none print:overflow-visible print:block">
        <div className="flex items-center justify-between p-4 border-b bg-muted/20 print:hidden shrink-0">
          <h3 className="font-semibold flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Generated Quiz
          </h3>
          <ExportButtons markdown={markdown} />
        </div>
        <div className="flex-1 overflow-auto p-6 md:p-8 bg-background print:bg-white print:p-0 print:block print:overflow-visible">
          <div className="prose prose-slate dark:prose-invert max-w-none print:!prose-slate print:max-w-full">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
              {markdown}
            </ReactMarkdown>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col h-full overflow-hidden print:border-none print:shadow-none print:overflow-visible print:block">
      <div className="flex items-center justify-between p-4 border-b bg-muted/20 print:hidden shrink-0">
        <h3 className="font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Interactive Quiz
        </h3>
        <div className="flex items-center gap-4">
          <ExportButtons markdown={markdown} />
        </div>
      </div>
      
      <div className="flex-1 overflow-auto p-6 md:p-8 bg-background print:bg-white print:p-0 print:block print:overflow-visible">
        <div className="max-w-4xl mx-auto space-y-8 pb-20">
          {submitted && (
            <div className="bg-primary/10 border-primary/20 border p-4 rounded-xl text-center flex flex-col items-center gap-2">
              <h2 className="text-2xl font-bold text-primary">
                {calculateCorrect()} / {quiz.length} Correct
              </h2>
            </div>
          )}

          {quiz.map((q, idx) => (
            <div key={q.id} className="bg-card border rounded-xl p-6 shadow-sm space-y-6">
              <div className="prose prose-slate dark:prose-invert max-w-none print:!prose-slate">
                <h4 className="text-lg font-medium mb-4 flex gap-2">
                  <span className="text-muted-foreground whitespace-nowrap">Question {idx + 1}.</span>
                  <div>
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {q.question || ""}
                    </ReactMarkdown>
                  </div>
                </h4>
              </div>

              <div className="space-y-3">
                {q.options.map((opt, oIdx) => {
                  const isSelected = selectedAnswers[q.id] === oIdx;
                  const isCorrect = q.correct_answer === oIdx;
                  
                  let optionClass = "flex items-center gap-3 p-4 rounded-lg border-2 text-left w-full transition-all cursor-pointer ";
                  
                  if (!submitted) {
                    optionClass += isSelected 
                      ? "border-primary bg-primary/5 shadow-sm" 
                      : "border-muted hover:border-primary/50 hover:bg-muted/50";
                  } else {
                    optionClass = optionClass.replace("cursor-pointer", "cursor-default");
                    if (isCorrect) {
                      optionClass += "border-green-500 bg-green-500/10 text-green-900 dark:text-green-100";
                    } else if (isSelected && !isCorrect) {
                      optionClass += "border-red-500 bg-red-500/10 text-red-900 dark:text-red-100";
                    } else {
                      optionClass += "border-muted opacity-50";
                    }
                  }

                  return (
                    <button
                      key={oIdx}
                      onClick={() => handleSelect(q.id, oIdx)}
                      disabled={submitted}
                      className={optionClass}
                    >
                      <div className="flex-1">
                        <div className="prose prose-slate dark:prose-invert max-w-none print:!prose-slate">
                          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                            {opt}
                          </ReactMarkdown>
                        </div>
                      </div>
                      {submitted && isCorrect && <CheckCircle2 className="w-5 h-5 text-green-600" />}
                      {submitted && isSelected && !isCorrect && <XCircle className="w-5 h-5 text-red-600" />}
                    </button>
                  );
                })}
              </div>

              {submitted && (
                <div className="pt-4 border-t mt-6">
                  <button 
                    onClick={() => toggleExplanation(q.id)}
                    className="text-sm font-medium text-primary hover:underline"
                  >
                    {expandedExplanations[q.id] ? "Hide Explanation" : "Show Explanation"}
                  </button>

                  {expandedExplanations[q.id] && (
                    <div className="mt-4 p-4 bg-muted/50 rounded-lg prose prose-slate dark:prose-invert max-w-none text-sm print:!prose-slate">
                      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {"**Explanation:**\n\n" + (q.explanation || "No explanation provided.")}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {!submitted && (
            <div className="flex justify-center pt-6">
              <button
                onClick={handleSubmit}
                disabled={Object.keys(selectedAnswers).length < quiz.length}
                className="px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg shadow-sm hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                Submit Quiz
              </button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
