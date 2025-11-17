import { useState, useEffect, useRef } from 'react';
import { Card } from '../../components/Card';
import { useLogs } from '../../hooks/useApi';

const LOG_LEVELS = ['ALL', 'INFO', 'WARN', 'ERROR', 'DEBUG'] as const;
type LogLevel = typeof LOG_LEVELS[number];

const LOG_KINDS = ['all', 'engine', 'trades', 'signals', 'system'] as const;
type LogKind = typeof LOG_KINDS[number];

export function LogsPage() {
  const [levelFilter, setLevelFilter] = useState<LogLevel>('ALL');
  const [kindFilter, setKindFilter] = useState<LogKind>('all');
  const [searchText, setSearchText] = useState('');
  const [follow, setFollow] = useState(true);
  const [autoScrollPaused, setAutoScrollPaused] = useState(false);
  
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastScrollTop = useRef(0);
  
  // Build query params
  const queryParams = {
    limit: 500,
    level: levelFilter === 'ALL' ? undefined : levelFilter,
    kind: kindFilter === 'all' ? undefined : kindFilter,
    contains: searchText || undefined,
  };
  
  const { data: logsResponse, isLoading } = useLogs(queryParams);
  const logs = logsResponse?.logs || logsResponse?.entries || [];
  
  // Auto-scroll when new logs arrive and follow is enabled
  useEffect(() => {
    if (follow && !autoScrollPaused && scrollContainerRef.current) {
      const container = scrollContainerRef.current;
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      
      if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [logs, follow, autoScrollPaused]);
  
  // Handle manual scroll
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    
    const container = scrollContainerRef.current;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    const scrollingUp = container.scrollTop < lastScrollTop.current;
    
    lastScrollTop.current = container.scrollTop;
    
    // If user scrolls up, pause auto-scroll
    if (scrollingUp && !isNearBottom) {
      setAutoScrollPaused(true);
    } else if (isNearBottom) {
      setAutoScrollPaused(false);
    }
  };
  
  const getLevelColor = (level: string) => {
    const upper = level.toUpperCase();
    if (upper === 'ERROR') return 'text-negative';
    if (upper === 'WARN' || upper === 'WARNING') return 'text-warning';
    if (upper === 'INFO') return 'text-text-secondary';
    if (upper === 'DEBUG') return 'text-text-muted';
    return 'text-text-secondary';
  };
  
  const getLevelBg = (level: string) => {
    const upper = level.toUpperCase();
    if (upper === 'ERROR') return 'bg-negative/10';
    if (upper === 'WARN' || upper === 'WARNING') return 'bg-warning/10';
    return 'bg-transparent';
  };
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Logs</h1>
          <p className="text-text-secondary mt-1">Real-time system logs with filtering</p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFollow(!follow)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              follow
                ? 'bg-primary text-white'
                : 'bg-surface-light text-text-secondary hover:bg-surface'
            }`}
          >
            {follow ? '● Follow' : '○ Paused'}
          </button>
        </div>
      </div>
      
      {/* Filters */}
      <Card>
        <div className="flex flex-wrap gap-4">
          {/* Level Filter */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Level
            </label>
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value as LogLevel)}
              className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {LOG_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>
          
          {/* Kind Filter */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Category
            </label>
            <select
              value={kindFilter}
              onChange={(e) => setKindFilter(e.target.value as LogKind)}
              className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {LOG_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind.charAt(0).toUpperCase() + kind.slice(1)}
                </option>
              ))}
            </select>
          </div>
          
          {/* Search */}
          <div className="flex-1 min-w-[300px]">
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Search
            </label>
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Filter by message content..."
              className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
      </Card>
      
      {/* Auto-scroll pause indicator */}
      {autoScrollPaused && follow && (
        <div className="bg-warning/10 border border-warning/20 rounded-lg px-4 py-2 flex items-center justify-between">
          <span className="text-sm text-warning">
            Auto-scroll paused (scrolled up)
          </span>
          <button
            onClick={() => {
              setAutoScrollPaused(false);
              if (scrollContainerRef.current) {
                scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
              }
            }}
            className="text-sm text-warning hover:text-warning/80 underline"
          >
            Resume & scroll to bottom
          </button>
        </div>
      )}
      
      {/* Logs Viewer */}
      <Card title={`Logs (${logs.length})`}>
        {isLoading && logs.length === 0 ? (
          <div className="text-center text-text-secondary py-12">
            Loading logs...
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center text-text-secondary py-12">
            <p>No logs found matching filters.</p>
            <p className="text-sm mt-2">Try adjusting your filters or wait for new logs.</p>
          </div>
        ) : (
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="h-[600px] overflow-y-auto font-mono text-xs"
            style={{
              scrollBehavior: autoScrollPaused ? 'auto' : 'smooth'
            }}
          >
            {logs.map((log, index) => (
              <div
                key={index}
                className={`flex gap-3 px-3 py-2 border-b border-border/50 hover:bg-surface-light/50 transition-colors ${getLevelBg(log.level)}`}
              >
                {/* Timestamp */}
                <div className="text-text-muted flex-shrink-0 w-[180px]">
                  {log.timestamp || log.ts || ''}
                </div>
                
                {/* Level */}
                <div className={`flex-shrink-0 w-[60px] font-semibold ${getLevelColor(log.level)}`}>
                  {log.level || 'INFO'}
                </div>
                
                {/* Source/Logger */}
                <div className="text-text-secondary flex-shrink-0 w-[150px] truncate">
                  {log.source || log.logger || ''}
                </div>
                
                {/* Message */}
                <div className="flex-1 text-text break-all">
                  {log.message || log.raw || ''}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
