import { useLocation } from 'react-router-dom';
import { useMeta } from '../hooks/useApi';
import { formatTime } from '../utils/format';
import { ConnectionStatus } from './ConnectionStatus';

const pageTitles: Record<string, string> = {
  '/': 'Overview',
  '/trading': 'Trading',
  '/portfolio': 'Portfolio',
  '/signals': 'Signals',
  '/analytics': 'Analytics',
  '/risk': 'Risk',
  '/system': 'System',
  '/logs': 'Logs',
};

export function TopBar() {
  const location = useLocation();
  const { data: meta } = useMeta();
  
  const pageTitle = pageTitles[location.pathname] || 'Dashboard';
  const mode = meta?.status_payload?.label || 'IDLE';
  const modeClass = 
    mode === 'OPEN' ? 'bg-positive text-white' :
    mode === 'PRE-MARKET' ? 'bg-warning text-white' :
    mode === 'CLOSED' ? 'bg-muted text-white' :
    'bg-muted text-white';
  
  return (
    <div className="h-16 bg-surface border-b border-border flex items-center justify-between px-6">
      {/* Left side - Page title */}
      <div className="flex items-center gap-4">
        <h2 className="text-xl font-semibold text-text-primary">{pageTitle}</h2>
      </div>
      
      {/* Right side */}
      <div className="flex items-center gap-6">
        {/* Connection Status */}
        <ConnectionStatus />
        
        {/* Mode Badge */}
        <div className={`px-4 py-2 rounded-md font-semibold text-sm ${modeClass}`}>
          {mode}
        </div>
        
        {/* Server Time */}
        <div className="text-right">
          <div className="text-xs text-text-secondary">Server Time (IST)</div>
          <div className="text-sm font-mono font-semibold text-text-primary">
            {formatTime(meta?.now_ist)}
          </div>
        </div>
      </div>
    </div>
  );
}
