import { Card, CardSkeleton } from '../../components/Card';
import { EngineLogsPanel } from '../../components/EngineLogsPanel';
import { useConfigSummary, useAuthStatus } from '../../hooks/useApi';

export function SystemPage() {
  const { data: config, isLoading: configLoading } = useConfigSummary();
  const { data: auth } = useAuthStatus();
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">System</h1>
      
      {/* System Info */}
      <Card title="System Information">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-text-secondary mb-1">Mode</div>
            <div className="font-semibold uppercase">{config?.mode || 'UNKNOWN'}</div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">Risk Profile</div>
            <div className="font-semibold">{config?.risk_profile || '--'}</div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">Auth Status</div>
            <div className={`font-semibold ${auth?.is_logged_in ? 'text-positive' : 'text-negative'}`}>
              {auth?.is_logged_in ? '✓ Logged In' : '✗ Not Logged In'}
            </div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">User ID</div>
            <div className="font-mono text-sm">{auth?.user_id || '--'}</div>
          </div>
        </div>
      </Card>
      
      {/* Config Summary */}
      {configLoading ? (
        <CardSkeleton />
      ) : (
        <Card title="Configuration">
          <div className="space-y-4">
            <div>
              <div className="text-sm text-text-secondary mb-1">Config Path</div>
              <div className="font-mono text-sm">{config?.config_path}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">FNO Universe</div>
              <div className="flex gap-2 flex-wrap">
                {config?.fno_universe.map((item, idx) => (
                  <span key={idx} className="px-3 py-1 bg-surface-light rounded text-sm font-semibold">
                    {item}
                  </span>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-sm text-text-secondary mb-1">Paper Capital</div>
                <div className="font-semibold">
                  ₹{config?.paper_capital.toLocaleString('en-IN')}
                </div>
              </div>
              <div>
                <div className="text-sm text-text-secondary mb-1">Risk Per Trade</div>
                <div className="font-semibold">{config?.risk_per_trade_pct}%</div>
              </div>
              <div>
                <div className="text-sm text-text-secondary mb-1">Max Daily Loss</div>
                <div className="font-semibold">
                  ₹{config?.max_daily_loss.toLocaleString('en-IN')}
                </div>
              </div>
              <div>
                <div className="text-sm text-text-secondary mb-1">Max Exposure</div>
                <div className="font-semibold">{config?.max_exposure_pct}x</div>
              </div>
            </div>
          </div>
        </Card>
      )}
      
      {/* Engine Logs Panel */}
      <div>
        <h2 className="text-2xl font-bold mb-4">Engine Logs</h2>
        <EngineLogsPanel />
      </div>
      
      {/* Raw Config JSON */}
      <Card title="Raw Configuration (Debug)">
        <details className="cursor-pointer">
          <summary className="text-text-secondary hover:text-text-primary">
            Click to expand full config JSON
          </summary>
          <pre className="mt-4 bg-background p-4 rounded text-xs overflow-x-auto scrollbar-thin">
            {JSON.stringify(config, null, 2)}
          </pre>
        </details>
      </Card>
    </div>
  );
}
