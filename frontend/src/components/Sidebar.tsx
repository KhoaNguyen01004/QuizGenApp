'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BrainCircuit, History, Settings, FileBox } from 'lucide-react';
import { cn } from '@/lib/utils';

const navItems = [
  { href: '/', icon: FileBox, label: 'New Generation' },
  { href: '/history', icon: History, label: 'History' },
  { href: '#', icon: Settings, label: 'Settings' },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r bg-muted/30 flex flex-col hidden md:flex print:hidden">
      <div className="h-14 border-b flex items-center px-4 gap-2">
        <div className="p-1.5 bg-primary rounded-md text-primary-foreground">
          <BrainCircuit className="h-5 w-5" />
        </div>
        <span className="font-bold text-lg">QuizGen AI</span>
      </div>

      <nav className="flex-1 p-4 space-y-2">
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = href === '/' ? pathname === '/' : pathname.startsWith(href);
          return (
            <Link
              key={label}
              href={href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md font-medium text-sm transition-colors',
                isActive
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-muted',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
