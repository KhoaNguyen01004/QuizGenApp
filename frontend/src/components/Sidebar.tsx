import { BrainCircuit, History, Settings, FileBox } from "lucide-react";

export function Sidebar() {
  return (
    <aside className="w-64 border-r bg-muted/30 flex flex-col hidden md:flex print:hidden">
      <div className="h-14 border-b flex items-center px-4 gap-2">
        <div className="p-1.5 bg-primary rounded-md text-primary-foreground print:hidden">
          <BrainCircuit className="h-5 w-5" />
        </div>
        <span className="font-bold text-lg">QuizGen AI</span>
      </div>
      <nav className="flex-1 p-4 space-y-2">
        <a href="#" className="flex items-center gap-3 px-3 py-2 bg-primary/10 text-primary rounded-md font-medium text-sm">
          <FileBox className="h-4 w-4" />
          New Generation
        </a>
        <a href="#" className="flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted rounded-md font-medium text-sm transition-colors">
          <History className="h-4 w-4" />
          History
        </a>
        <a href="#" className="flex items-center gap-3 px-3 py-2 text-muted-foreground hover:bg-muted rounded-md font-medium text-sm transition-colors">
          <Settings className="h-4 w-4" />
          Settings
        </a>
      </nav>
    </aside>
  );
}
