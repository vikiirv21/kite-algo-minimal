import { useMeta } from '../hooks/useApi';
import { formatTime } from '../utils/format';

export function TopBar() {
  const { data: meta } = useMeta();
  
  const mode = meta?.status_payload?.label || 'IDLE';
  const modeClass = 
    mode === 'OPEN' ? 'bg-positive text-white' :
    mode === 'PRE-MARKET' ? 'bg-warning text-white' :
    'bg-muted text-white';
  
  return (
    <div className="h-16 bg-surface border-b border-border flex items-center justify-between px-6">
      {/* Left side - can show current page title */}
      <div className="flex items-center gap-4">
        <h2 className="text-xl font-semibold">Dashboard</h2>
      </div>
      
      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Mode Badge */}
        <div className={`px-4 py-2 rounded-md font-semibold text-sm ${modeClass}`}>
          {mode}
        </div>
        
        {/* Server Time */}
        <div className="text-right">
          <div className="text-xs text-text-secondary">Server Time</div>
          <div className="text-sm font-mono font-semibold">
            {formatTime(meta?.now_ist)} IST
          </div>
        </div>
      </div>
    </div>
  );
}
