/**
 * Risk Dashboard Page
 * 
 * Backend APIs used:
 * - GET /api/risk/summary - Risk configuration and current halt status
 * - GET /api/portfolio/summary - Current exposure and position data
 * - GET /api/config/summary - Risk limits and configuration
 * - GET /api/summary/today - Today's P&L for loss limit calculation
 * 
 * Missing fields:
 * - max_positions: Currently hardcoded, should come from config
 * 
 * Missing features (for future enhancement):
 * - Per-symbol position limits
 * - Correlation-adjusted exposure
 * - Value at Risk (VaR) calculations
 * - Real-time risk alerts
 */

import { Card } from '../../components/Card';
import { usePortfolioSummary, useConfigSummary, useTodaySummary, useRiskSummary } from '../../hooks/useApi';
import { formatCurrency, formatPercent, getPnlClass } from '../../utils/format';
import { AdvancedRiskMetrics } from './AdvancedRiskMetrics';

// Helper function to get risk level color
function getRiskLevelColor(percentUsed: number): string {
  if (percentUsed >= 90) return 'bg-negative';
  if (percentUsed >= 60) return 'bg-warning';
  return 'bg-positive';
}

// Helper function to get risk level status
function getRiskLevelStatus(percentUsed: number): { text: string; class: string } {
  if (percentUsed >= 90) return { text: '✗ Critical level', class: 'text-negative' };
  if (percentUsed >= 60) return { text: '⚠ Approaching limit', class: 'text-warning' };
  return { text: '✓ Within safe limits', class: 'text-positive' };
}

export function RiskPage() {
  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolioSummary();
  const { data: config, isLoading: configLoading, error: configError } = useConfigSummary();
  const { data: today, isLoading: todayLoading, error: todayError } = useTodaySummary();
  const { data: riskSummary, isLoading: riskLoading, error: riskError } = useRiskSummary();
  
  // Show loading state while any critical data is loading
  const isLoading = portfolioLoading || configLoading || todayLoading || riskLoading;
  
  // Show error if any critical API fails
  const hasError = portfolioError || configError || todayError || riskError;
  
  // Calculate risk metrics with safe defaults
  const maxDailyLoss = config?.max_daily_loss ?? 3000;
  const dailyPnl = today?.realized_pnl ?? 0;
  const lossUsed = Math.abs(Math.min(0, dailyPnl));
  const lossUsedPct = maxDailyLoss > 0 ? (lossUsed / maxDailyLoss) * 100 : 0;
  
  const maxExposure = config?.max_exposure_pct ?? 1;
  const currentExposure = portfolio?.exposure_pct ?? 0;
  const exposureUsedPct = maxExposure > 0 ? (currentExposure / maxExposure) * 100 : 0;
  
  // Get max_positions from config or portfolio (may be null for unlimited)
  const maxPositions = portfolio?.position_limit ?? config?.max_positions ?? null;
  const currentPositions = portfolio?.open_positions ?? portfolio?.position_count ?? 0;
  
  // Position limit handling: null or 0 means unlimited
  const isUnlimitedPositions = maxPositions === null || maxPositions === 0;
  const positionsUsedPct = isUnlimitedPositions ? 0 : (currentPositions / maxPositions) * 100;
  
  const lossStatus = getRiskLevelStatus(lossUsedPct);
  const exposureStatus = getRiskLevelStatus(exposureUsedPct);
  const positionStatus = getRiskLevelStatus(positionsUsedPct);
  
  // Show loading screen
  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Risk Dashboard</h1>
        <p className="text-text-secondary mt-2">
          Monitor risk metrics and limits in real-time
        </p>
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
            <p className="text-text-secondary">Loading risk metrics...</p>
          </div>
        </div>
      </div>
    );
  }
  
  // Show error state if APIs fail
  if (hasError) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Risk Dashboard</h1>
        <p className="text-text-secondary mt-2">
          Monitor risk metrics and limits in real-time
        </p>
        <div className="bg-negative/20 border-2 border-negative rounded-lg px-6 py-8">
          <div className="text-center">
            <span className="text-4xl mb-4 block">⚠️</span>
            <h2 className="text-xl font-bold text-negative mb-2">Unable to Load Risk Data</h2>
            <p className="text-text-secondary mb-4">
              There was an error loading risk metrics. Please check:
            </p>
            <ul className="text-left max-w-md mx-auto space-y-2 text-sm text-text-secondary">
              <li>• Dashboard backend is running</li>
              <li>• API endpoints are accessible</li>
              <li>• Trading engine is operational</li>
            </ul>
            {(portfolioError || configError || todayError || riskError) && (
              <div className="mt-4 text-xs text-left max-w-md mx-auto bg-surface-light p-3 rounded">
                <p className="font-semibold mb-1">Error Details:</p>
                {portfolioError && <p>Portfolio: {String(portfolioError)}</p>}
                {configError && <p>Config: {String(configError)}</p>}
                {todayError && <p>Today: {String(todayError)}</p>}
                {riskError && <p>Risk: {String(riskError)}</p>}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Risk Dashboard</h1>
        <p className="text-text-secondary mt-2">
          Monitor risk metrics and limits in real-time
        </p>
        
        {/* Trading Halted Alert */}
        {riskSummary?.trading_halted && (
          <div className="mt-4 bg-negative/20 border-2 border-negative rounded-lg px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">⚠️</span>
              <div>
                <div className="font-bold text-negative text-lg">TRADING HALTED</div>
                <div className="text-sm text-text-secondary mt-1">
                  Reason: {riskSummary.halt_reason || 'Unknown'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      
      {/* Risk Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Daily Loss Limit */}
        <Card title="Daily Loss Limit">
          <div className="space-y-4">
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-2xl font-bold">{formatCurrency(lossUsed)}</span>
                <span className="text-text-secondary text-sm">
                  of {formatCurrency(maxDailyLoss)}
                </span>
              </div>
              <div className="w-full bg-border rounded-full h-3">
                <div 
                  className={`rounded-full h-3 transition-all ${getRiskLevelColor(lossUsedPct)}`}
                  style={{ width: `${Math.min(100, lossUsedPct)}%` }}
                />
              </div>
              <div className="text-xs text-text-secondary mt-1">
                {lossUsedPct.toFixed(1)}% used
              </div>
            </div>
            <div className={`text-sm ${lossStatus.class}`}>
              {lossStatus.text}
            </div>
          </div>
        </Card>
        
        {/* Exposure Limit */}
        <Card title="Exposure Limit">
          <div className="space-y-4">
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-2xl font-bold">{formatPercent(currentExposure * 100)}</span>
                <span className="text-text-secondary text-sm">
                  of {formatPercent(maxExposure * 100)}
                </span>
              </div>
              <div className="w-full bg-border rounded-full h-3">
                <div 
                  className={`rounded-full h-3 transition-all ${getRiskLevelColor(exposureUsedPct)}`}
                  style={{ width: `${Math.min(100, exposureUsedPct)}%` }}
                />
              </div>
              <div className="text-xs text-text-secondary mt-1">
                {exposureUsedPct.toFixed(1)}% used
              </div>
            </div>
            <div className="text-sm">
              <div className={exposureStatus.class}>{exposureStatus.text}</div>
              <div className="text-text-secondary mt-1">
                Notional: {formatCurrency(portfolio?.total_notional ?? 0)}
              </div>
            </div>
          </div>
        </Card>
        
        {/* Position Limit */}
        <Card title="Position Limit">
          <div className="space-y-4">
            {isUnlimitedPositions ? (
              // Unlimited positions case
              <>
                <div>
                  <div className="text-lg font-semibold mb-2">No hard limit configured</div>
                  <div className="text-text-secondary text-sm">
                    Open positions: {currentPositions}
                  </div>
                </div>
                <div className="text-sm text-positive">
                  ✓ Unlimited positions enabled
                </div>
              </>
            ) : (
              // Finite position limit case
              <>
                <div>
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-2xl font-bold">{currentPositions}</span>
                    <span className="text-text-secondary text-sm">
                      of {maxPositions} positions
                    </span>
                  </div>
                  <div className="w-full bg-border rounded-full h-3">
                    <div 
                      className={`rounded-full h-3 transition-all ${getRiskLevelColor(positionsUsedPct)}`}
                      style={{ width: `${Math.min(100, positionsUsedPct)}%` }}
                    />
                  </div>
                  <div className="text-xs text-text-secondary mt-1">
                    {positionsUsedPct.toFixed(1)}% used
                  </div>
                </div>
                <div className={`text-sm ${positionStatus.class}`}>
                  {positionStatus.text}
                  <div className="text-text-secondary mt-1">
                    {maxPositions - currentPositions} positions available
                  </div>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>
      
      {/* Risk Configuration */}
      <Card title="Risk Configuration">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <div className="text-sm text-text-secondary mb-1">Risk Profile</div>
            <div className="text-lg font-semibold">{config?.risk_profile ?? 'Conservative'}</div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">Risk Per Trade</div>
            <div className="text-lg font-semibold">{config?.risk_per_trade_pct ?? 0}%</div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">Paper Capital</div>
            <div className="text-lg font-semibold">{formatCurrency(config?.paper_capital ?? 0)}</div>
          </div>
          <div>
            <div className="text-sm text-text-secondary mb-1">Mode</div>
            <div className="text-lg font-semibold uppercase">{config?.mode ?? 'PAPER'}</div>
          </div>
        </div>
      </Card>
      
      {/* Capital at Risk */}
      <Card title="Capital at Risk">
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-sm text-text-secondary mb-1">Equity</div>
              <div className="text-xl font-bold">{formatCurrency(portfolio?.equity ?? 0)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Unrealized P&L</div>
              <div className={`text-xl font-bold ${getPnlClass(portfolio?.total_unrealized_pnl ?? 0)}`}>
                {formatCurrency(portfolio?.total_unrealized_pnl ?? 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Free Margin</div>
              <div className="text-xl font-bold">{formatCurrency(portfolio?.free_notional ?? 0)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Today's P&L</div>
              <div className={`text-xl font-bold ${getPnlClass(dailyPnl)}`}>
                {formatCurrency(dailyPnl)}
              </div>
            </div>
          </div>
        </div>
      </Card>
      
      {/* Advanced Risk Metrics */}
      <AdvancedRiskMetrics />
    </div>
  );
}
