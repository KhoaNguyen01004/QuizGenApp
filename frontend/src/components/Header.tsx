import { ThemeToggle } from "@/components/ThemeToggle";

export function Header() {
  return (
    <header className="h-14 border-b flex items-center px-6 justify-between bg-background/95 backdrop-blur z-10 print:hidden">
      <h1 className="font-semibold">Dashboard</h1>
      <ThemeToggle />
    </header>
  );
}
