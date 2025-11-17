import { useLocation } from 'react-router-dom';
import { useMeta, useEnginesStatus } from '../hooks/useApi';
import { formatTime } from '../utils/format';
import { deriveModeFromEngines, getModeBadgeClass } from '../utils/mode';
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
  const { data: enginesData } = useEnginesStatus();
  
  const pageTitle = pageTitles[location.pathname] || 'Dashboard';
  
  // Derive mode from engines (LIVE/PAPER/IDLE)
  const tradingMode = deriveModeFromEngines(enginesData?.engines);
  const tradingModeClass = getModeBadgeClass(tradingMode);
  
  // Market status (OPEN/PRE-MARKET/CLOSED)
  const marketStatus = meta?.status_payload?.label || 'UNKNOWN';
  const marketStatusClass = 
    marketStatus === 'OPEN' ? 'bg-positive text-white' :
    marketStatus === 'PRE-MARKET' ? 'bg-warning text-black' :
    'bg-surface-light text-text-secondary';
  
  return (
    <div className="h-16 bg-surface border-b border-border flex items-center justify-between px-6">
      {/* Left side - Page title */}
      <div className="flex items-center gap-4">
        <h2 className="text-xl font-semibold text-text-primary">{pageTitle}</h2>
      </div>
      
      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Connection Status */}
        <ConnectionStatus />
        
        {/* Trading Mode Badge (LIVE/PAPER/IDLE) */}
        <div className={`px-3 py-1.5 rounded-md font-bold text-xs uppercase ${tradingModeClass}`}>
          {tradingMode}
        </div>
        
        {/* Market Status Badge */}
        <div className={`px-3 py-1.5 rounded-md font-semibold text-xs ${marketStatusClass}`}>
          {marketStatus}
        </div>
        
        {/* Server Time */}
        <div className="text-right">
          <div className="text-xs text-text-secondary">IST</div>
          <div className="text-sm font-mono font-semibold text-text-primary">
            {formatTime(meta?.now_ist)}
          </div>
        </div>
      </div>
    </div>
  );
}
