import { Card, CardSkeleton } from '../../components/Card';
import { usePortfolioSummary, useConfigSummary, useTodaySummary, useRiskSummary } from '../../hooks/useApi';
import { formatCurrency, formatPercent, getPnlClass } from '../../utils/format';

export function RiskPage() {
  const { data: portfolio, isLoading: portfolioLoading } = usePortfolioSummary();
  const { data: config, isLoading: configLoading } = useConfigSummary();
  const { data: today } = useTodaySummary();
  const { data: riskSummary } = useRiskSummary();
  
  // Calculate risk metrics
  const maxDailyLoss = config?.max_daily_loss || 3000;
  const dailyPnl = today?.realized_pnl || 0;
  const lossUsed = Math.abs(Math.min(0, dailyPnl));
  const lossUsedPct = (lossUsed / maxDailyLoss) * 100;
  
  const maxExposure = config?.max_exposure_pct || 1;
  const currentExposure = portfolio?.exposure_pct || 0;
  const exposureUsedPct = (currentExposure / maxExposure) * 100;
  
  const maxPositions = 5; // TODO: Get from config
  const currentPositions = portfolio?.position_count || 0;
  const positionsUsedPct = (currentPositions / maxPositions) * 100;
  
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
        {configLoading ? (
          <CardSkeleton />
        ) : (
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
                    className={`rounded-full h-3 transition-all ${
                      lossUsedPct < 50 ? 'bg-positive' : 
                      lossUsedPct < 80 ? 'bg-warning' : 
                      'bg-negative'
                    }`}
                    style={{ width: `${Math.min(100, lossUsedPct)}%` }}
                  />
                </div>
              </div>
              <div className="text-sm text-text-secondary">
                {lossUsedPct < 80 ? (
                  <span className="text-positive">✓ Within safe limits</span>
                ) : lossUsedPct < 100 ? (
                  <span className="text-warning">⚠ Approaching limit</span>
                ) : (
                  <span className="text-negative">✗ Limit exceeded</span>
                )}
              </div>
            </div>
          </Card>
        )}
        
        {/* Exposure Limit */}
        {portfolioLoading ? (
          <CardSkeleton />
        ) : (
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
                    className={`rounded-full h-3 transition-all ${
                      exposureUsedPct < 50 ? 'bg-positive' : 
                      exposureUsedPct < 80 ? 'bg-warning' : 
                      'bg-negative'
                    }`}
                    style={{ width: `${Math.min(100, exposureUsedPct)}%` }}
                  />
                </div>
              </div>
              <div className="text-sm text-text-secondary">
                Notional: {formatCurrency(portfolio?.total_notional)}
              </div>
            </div>
          </Card>
        )}
        
        {/* Position Limit */}
        <Card title="Position Limit">
          <div className="space-y-4">
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-2xl font-bold">{currentPositions}</span>
                <span className="text-text-secondary text-sm">
                  of {maxPositions} positions
                </span>
              </div>
              <div className="w-full bg-border rounded-full h-3">
                <div 
                  className={`rounded-full h-3 transition-all ${
                    positionsUsedPct < 80 ? 'bg-positive' : 'bg-warning'
                  }`}
                  style={{ width: `${Math.min(100, positionsUsedPct)}%` }}
                />
              </div>
            </div>
            <div className="text-sm text-text-secondary">
              {maxPositions - currentPositions} positions available
            </div>
          </div>
        </Card>
      </div>
      
      {/* Risk Configuration */}
      <Card title="Risk Configuration">
        {configLoading ? (
          <CardSkeleton />
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-sm text-text-secondary mb-1">Risk Profile</div>
              <div className="text-lg font-semibold">{config?.risk_profile || 'Conservative'}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Risk Per Trade</div>
              <div className="text-lg font-semibold">{config?.risk_per_trade_pct}%</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Paper Capital</div>
              <div className="text-lg font-semibold">{formatCurrency(config?.paper_capital)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Mode</div>
              <div className="text-lg font-semibold uppercase">{config?.mode || 'PAPER'}</div>
            </div>
          </div>
        )}
      </Card>
      
      {/* Capital at Risk */}
      <Card title="Capital at Risk">
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-sm text-text-secondary mb-1">Equity</div>
              <div className="text-xl font-bold">{formatCurrency(portfolio?.equity)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Unrealized P&L</div>
              <div className={`text-xl font-bold ${getPnlClass(portfolio?.total_unrealized_pnl)}`}>
                {formatCurrency(portfolio?.total_unrealized_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Free Margin</div>
              <div className="text-xl font-bold">{formatCurrency(portfolio?.free_notional)}</div>
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
      
      {/* Future Enhancements */}
      <Card title="Advanced Risk Metrics (Coming Soon)">
        <div className="text-center text-text-secondary py-8">
          <p className="font-semibold">Additional Risk Features Planned:</p>
          <ul className="mt-4 space-y-2 text-sm text-left max-w-2xl mx-auto">
            <li>• Max drawdown monitoring</li>
            <li>• Per-symbol position limits</li>
            <li>• Correlation-adjusted exposure</li>
            <li>• Value at Risk (VaR) calculations</li>
            <li>• Real-time risk alerts and notifications</li>
          </ul>
          <pre className="mt-6 text-left inline-block bg-surface-light p-4 rounded text-xs">
{`// Expected API endpoints:
GET /api/risk/limits        // All risk limits
GET /api/risk/breaches      // Current limit breaches
GET /api/risk/var           // Value at Risk metrics
POST /api/risk/limits       // Update risk limits`}
          </pre>
        </div>
      </Card>
    </div>
  );
}
