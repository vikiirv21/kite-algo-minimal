import { useState, useEffect, useRef } from 'react';
import { Card } from './Card';
import { useEngineLogs } from '../hooks/useApi';

type EngineType = 'fno' | 'equity' | 'options';

const ENGINE_TABS: { id: EngineType; label: string }[] = [
  { id: 'fno', label: 'FNO' },
  { id: 'equity', label: 'Equity' },
  { id: 'options', label: 'Options' },
];

export function EngineLogsPanel() {
  const [activeEngine, setActiveEngine] = useState<EngineType>('fno');
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const prevLinesCountRef = useRef(0);

  // Only fetch logs for the active engine
  const { data: logsData, isLoading } = useEngineLogs(
    activeEngine,
    200,
    true // Always enabled
  );

  const lines = logsData?.lines || [];
  const warning = logsData?.warning;
  const exists = logsData?.exists ?? true;

  // Auto-scroll when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      const container = logContainerRef.current;
      const isNewContent = lines.length > prevLinesCountRef.current;
      
      if (isNewContent) {
        // Smooth scroll to bottom
        container.scrollTop = container.scrollHeight;
      }
    }
    prevLinesCountRef.current = lines.length;
  }, [lines, autoScroll]);

  // Handle manual scroll - disable auto-scroll if user scrolls up
  const handleScroll = () => {
    if (!logContainerRef.current) return;
    
    const container = logContainerRef.current;
    const isAtBottom = 
      container.scrollHeight - container.scrollTop - container.clientHeight < 50;
    
    // Update auto-scroll based on scroll position
    if (!isAtBottom && autoScroll) {
      setAutoScroll(false);
    } else if (isAtBottom && !autoScroll) {
      setAutoScroll(true);
    }
  };

  const scrollToBottom = () => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      setAutoScroll(true);
    }
  };

  return (
    <Card>
      <div className="space-y-4">
        {/* Header with tabs and controls */}
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            {ENGINE_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveEngine(tab.id);
                  prevLinesCountRef.current = 0; // Reset on tab change
                }}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeEngine === tab.id
                    ? 'bg-primary text-white'
                    : 'bg-surface-light text-text-secondary hover:bg-surface'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          
          <div className="flex items-center gap-3">
            <span className="text-sm text-text-secondary">
              {lines.length} lines
            </span>
            <button
              onClick={() => setAutoScroll(!autoScroll)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                autoScroll
                  ? 'bg-positive/10 text-positive'
                  : 'bg-surface-light text-text-secondary'
              }`}
            >
              {autoScroll ? '● Auto-scroll ON' : '○ Auto-scroll OFF'}
            </button>
            {!autoScroll && (
              <button
                onClick={scrollToBottom}
                className="px-3 py-1 rounded text-xs font-medium bg-primary/10 text-primary hover:bg-primary/20"
              >
                ↓ Jump to bottom
              </button>
            )}
          </div>
        </div>

        {/* Warning message if log file doesn't exist */}
        {!exists && warning && (
          <div className="bg-warning/10 border border-warning/20 rounded-lg px-4 py-3">
            <p className="text-sm text-warning">⚠️ {warning}</p>
          </div>
        )}

        {/* Loading state */}
        {isLoading && lines.length === 0 ? (
          <div className="text-center text-text-secondary py-12">
            Loading logs...
          </div>
        ) : lines.length === 0 ? (
          <div className="text-center text-text-secondary py-12">
            <p>No logs available for {activeEngine} engine.</p>
            <p className="text-sm mt-2">
              Logs will appear here when the engine is running.
            </p>
          </div>
        ) : (
          /* Log viewer with terminal styling */
          <div
            ref={logContainerRef}
            onScroll={handleScroll}
            className="h-[600px] overflow-y-auto bg-[#1e1e1e] rounded-lg p-4 font-mono text-sm"
            style={{
              scrollBehavior: autoScroll ? 'smooth' : 'auto',
            }}
          >
            {lines.map((line, index) => (
              <div
                key={index}
                className="text-[#d4d4d4] leading-relaxed hover:bg-[#2a2a2a] px-2 py-0.5 rounded"
              >
                {/* Syntax highlighting for log levels */}
                {line.includes('[INFO]') && (
                  <span className="text-[#4ec9b0]">{line}</span>
                )}
                {line.includes('[DEBUG]') && (
                  <span className="text-[#808080]">{line}</span>
                )}
                {line.includes('[WARN]') && (
                  <span className="text-[#dcdcaa]">{line}</span>
                )}
                {line.includes('[ERROR]') && (
                  <span className="text-[#f48771]">{line}</span>
                )}
                {!line.includes('[INFO]') && 
                 !line.includes('[DEBUG]') && 
                 !line.includes('[WARN]') && 
                 !line.includes('[ERROR]') && (
                  <span>{line}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
