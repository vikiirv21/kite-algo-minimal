import type { ReactNode } from 'react';
import { LastUpdated } from './LastUpdated';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
  lastUpdated?: number | null;
}

export function Card({ title, children, className = '', action, lastUpdated }: CardProps) {
  return (
    <div className={`bg-surface rounded-lg border border-border shadow-card overflow-hidden ${className}`}>
      {title && (
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
            {lastUpdated !== undefined && <LastUpdated timestamp={lastUpdated} />}
          </div>
          {action && <div>{action}</div>}
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
    <div className={`bg-surface rounded-lg border border-border shadow-card ${className}`}>
      <div className="p-6 space-y-4 animate-pulse">
        <div className="h-4 bg-border rounded w-3/4"></div>
        <div className="h-4 bg-border rounded w-1/2"></div>
        <div className="h-4 bg-border rounded w-5/6"></div>
      </div>
    </div>
  );
}

// Error display
export function CardError({ title, error }: { title?: string; error: Error | string }) {
  return (
    <Card title={title} className="border-negative/30">
      <div className="flex items-center gap-3 text-negative">
        <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
        </svg>
        <div>
          <div className="font-semibold">Failed to load data</div>
          <div className="text-sm text-text-secondary mt-1">
            {typeof error === 'string' ? error : error.message}
          </div>
        </div>
      </div>
    </Card>
  );
}
