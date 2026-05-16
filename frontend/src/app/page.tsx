'use client';

import { useEffect, useState, useRef } from "react";
import { UploadZone } from "@/components/UploadZone";
import { QuizForm } from "@/components/QuizForm";
import { PipelineStatus } from "@/components/PipelineStatus";
import { LogsPanel } from "@/components/LogsPanel";
import { QuizViewer } from "@/components/QuizViewer";
import { useStore } from "@/store/useStore";
import { api } from "@/services/api";
import { toast } from "sonner";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const store = useStore();
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (store.jobId && store.isProcessing) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await api.getStatus(store.jobId!);
          store.updateStatus(status.stage, status.progress, status.logs);
          
          if (status.progress >= 100 || status.stage?.toLowerCase() === 'complete') {
            clearInterval(pollIntervalRef.current!);
            fetchResult(store.jobId!);
          }
        } catch (error) {
          console.error(error);
          store.setError("Failed to fetch status");
          toast.error("Lost connection to processing server");
          clearInterval(pollIntervalRef.current!);
        }
      }, 2000);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [store.jobId, store.isProcessing]);

  const fetchResult = async (jobId: string) => {
    try {
      const result = await api.getResult(jobId);
      store.setResult(result.markdown);
      toast.success("Quiz generated successfully!");
    } catch (error) {
      console.error(error);
      store.setError("Failed to fetch result");
      toast.error("Failed to load generated quiz");
    }
  };

  const handleGenerate = async (mode: any, numQs: number) => {
    if (!file) {
      toast.error("Please upload a PDF file first");
      return;
    }

    try {
      store.reset();
      store.setJobId("temp-id");
      const response = await api.generateQuiz(file, mode, numQs);
      store.setJobId(response.job_id);
      toast.success("Generation started!");
    } catch (error) {
      console.error(error);
      store.reset();
      toast.error("Failed to start generation. Make sure backend is running.");
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden print:h-auto print:bg-white print:text-black">
      <Sidebar />

      <main className="flex-1 flex flex-col overflow-hidden relative print:block print:overflow-visible">
        <Header />

        <div className="flex-1 overflow-auto p-6 md:p-8 print:p-0 print:overflow-visible print:block">
          <div className="max-w-6xl mx-auto space-y-8 print:space-y-0 print:max-w-none">
            
            {!store.markdown && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 print:hidden">
                <div className="lg:col-span-7 xl:col-span-8 space-y-6">
                  <div>
                    <h2 className="text-2xl font-bold tracking-tight mb-4">Create New Quiz</h2>
                    <UploadZone onFileSelect={setFile} />
                  </div>
                  
                  <QuizForm 
                    onGenerate={handleGenerate} 
                    disabled={!file || store.isProcessing} 
                  />
                </div>

                <div className="lg:col-span-5 xl:col-span-4 space-y-6">
                  {store.isProcessing && (
                    <>
                      <PipelineStatus stage={store.stage} progress={store.progress} />
                      <div className="h-[400px]">
                        <LogsPanel logs={store.logs} />
                      </div>
                    </>
                  )}
                  
                  {!store.isProcessing && store.error && (
                    <div className="p-4 bg-red-500/15 border border-red-500/30 text-red-500 rounded-lg text-sm">
                      <strong>Error:</strong> {store.error}
                    </div>
                  )}
                </div>
              </div>
            )}

            {store.markdown && (
              <div className="h-[calc(100vh-8rem)] print:h-auto print:block">
                <QuizViewer markdown={store.markdown} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
