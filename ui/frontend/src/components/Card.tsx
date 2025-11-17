import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Card({ title, children, className = '' }: CardProps) {
  return (
    <div className={`bg-surface rounded-lg border border-border overflow-hidden ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-border">
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
      )}
      <div className="p-6">
        {children}
      </div>
    </div>
  );
}

// Loading skeleton
export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-surface rounded-lg border border-border ${className}`}>
      <div className="p-6 space-y-4 animate-pulse">
        <div className="h-4 bg-border rounded w-3/4"></div>
        <div className="h-4 bg-border rounded w-1/2"></div>
        <div className="h-4 bg-border rounded w-5/6"></div>
      </div>
    </div>
  );
}
