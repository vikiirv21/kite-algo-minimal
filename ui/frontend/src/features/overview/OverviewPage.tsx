import { Card, CardSkeleton, CardError } from '../../components/Card';
import {
  useEnginesStatus,
  usePortfolioSummary,
  useRecentSignals,
  useTodaySummary,
} from '../../hooks/useApi';
import { formatCurrency, formatTimestamp, formatPercent, getPnlClass, getPnlPrefix } from '../../utils/format';

export function OverviewPage() {
  const { data: engines, isLoading: enginesLoading, error: enginesError } = useEnginesStatus();
  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolioSummary();
  const { data: signals, isLoading: signalsLoading, error: signalsError } = useRecentSignals(10);
  const { data: today, isLoading: todayLoading, error: todayError } = useTodaySummary();
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Overview</h1>
      
      {/* Top Row - Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Mode & Engines */}
        {enginesLoading ? (
          <CardSkeleton />
        ) : enginesError ? (
          <CardError title="Engines Status" error={enginesError} />
        ) : (
          <Card title="Engines Status">
            {engines?.engines && engines.engines.length > 0 ? (
              engines.engines.map((engine) => (
                <div key={engine.engine} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-text-secondary">Mode:</span>
                    <span className="font-semibold uppercase">{engine.mode}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-text-secondary">Status:</span>
                    <span className={engine.running ? 'text-positive' : 'text-negative'}>
                      {engine.running ? '● Running' : '○ Stopped'}
                    </span>
                  </div>
                  {engine.checkpoint_age_seconds !== null && (
                    <div className="text-xs text-text-secondary">
                      Last update: {engine.checkpoint_age_seconds}s ago
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-text-secondary text-sm">No engines configured</div>
            )}
          </Card>
        )}
        
        {/* Portfolio Snapshot */}
        {portfolioLoading ? (
          <CardSkeleton />
        ) : portfolioError ? (
          <CardError title="Portfolio" error={portfolioError} />
        ) : (
          <Card title="Portfolio">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Equity:</span>
                <span className="font-semibold">{formatCurrency(portfolio?.equity)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Daily P&L:</span>
                <span className={`font-semibold ${getPnlClass(portfolio?.daily_pnl)}`}>
                  {getPnlPrefix(portfolio?.daily_pnl)}{formatCurrency(portfolio?.daily_pnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Positions:</span>
                <span className="font-semibold">{portfolio?.position_count || 0}</span>
              </div>
              {portfolio?.exposure_pct !== null && portfolio?.exposure_pct !== undefined && (
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Exposure:</span>
                  <span className="font-semibold">{formatPercent(portfolio.exposure_pct * 100)}</span>
                </div>
              )}
            </div>
          </Card>
        )}
        
        {/* Today's Summary */}
        {todayLoading ? (
          <CardSkeleton />
        ) : todayError ? (
          <CardError title="Today's Trading" error={todayError} />
        ) : (
          <Card title="Today's Trading">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Realized P&L:</span>
                <span className={`font-semibold ${getPnlClass(today?.realized_pnl)}`}>
                  {getPnlPrefix(today?.realized_pnl)}{formatCurrency(today?.realized_pnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Trades:</span>
                <span className="font-semibold">{today?.num_trades || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Win Rate:</span>
                <span className="font-semibold">{formatPercent(today?.win_rate)}</span>
              </div>
              {today?.avg_r !== undefined && (
                <div className="flex items-center justify-between">
                  <span className="text-text-secondary">Avg R:</span>
                  <span className={`font-semibold ${getPnlClass(today.avg_r)}`}>
                    {today.avg_r.toFixed(2)}R
                  </span>
                </div>
              )}
            </div>
          </Card>
        )}
        
        {/* Risk Budget */}
        <Card title="Risk Budget">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">Max Daily Loss:</span>
              <span className="font-semibold">{formatCurrency(3000)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-text-secondary">Used:</span>
              <span className="font-semibold">
                {formatCurrency(Math.abs(Math.min(0, today?.realized_pnl || 0)))}
              </span>
            </div>
            <div className="w-full bg-border rounded-full h-2 mt-2">
              <div 
                className="bg-warning rounded-full h-2 transition-all"
                style={{ 
                  width: `${Math.min(100, Math.abs(Math.min(0, today?.realized_pnl || 0)) / 3000 * 100)}%` 
                }}
              ></div>
            </div>
          </div>
        </Card>
      </div>
      
      {/* Recent Signals */}
      {signalsError ? (
        <CardError title="Recent Signals" error={signalsError} />
      ) : (
        <Card title="Recent Signals">
          {signalsLoading ? (
            <div className="space-y-2">
              <div className="h-4 bg-border rounded animate-pulse"></div>
              <div className="h-4 bg-border rounded animate-pulse"></div>
            </div>
          ) : !signals || signals.length === 0 ? (
            <div className="text-center text-text-secondary py-8">No signals yet</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="pb-2 text-text-secondary font-medium">Time</th>
                    <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                    <th className="pb-2 text-text-secondary font-medium">Direction</th>
                    <th className="pb-2 text-text-secondary font-medium">Strategy</th>
                    <th className="pb-2 text-text-secondary font-medium text-right">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal, idx) => (
                    <tr key={idx} className="border-b border-border/50 hover:bg-surface-light">
                      <td className="py-2 text-sm">{formatTimestamp(signal.ts)}</td>
                      <td className="py-2 font-medium">{signal.symbol}</td>
                      <td className="py-2">
                        <span className={`
                          px-2 py-1 rounded text-xs font-semibold
                          ${signal.signal === 'BUY' ? 'bg-positive/20 text-positive' : 
                            signal.signal === 'SELL' ? 'bg-negative/20 text-negative' : 
                            'bg-muted/20 text-muted'}
                        `}>
                          {signal.signal}
                        </span>
                      </td>
                      <td className="py-2 text-sm text-text-secondary">{signal.strategy}</td>
                      <td className="py-2 text-sm text-right font-mono">
                        {signal.price ? `₹${signal.price.toFixed(2)}` : '--'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
