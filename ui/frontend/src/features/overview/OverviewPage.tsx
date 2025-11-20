import { Card, CardSkeleton, CardError } from '../../components/Card';
import {
  useEnginesStatus,
  usePortfolioSummary,
  useRecentSignals,
  useTodaySummary,
  useAnalyticsSummary,
} from '../../hooks/useApi';
import { formatCurrency, formatTimestamp, formatPercent, getPnlClass, getPnlPrefix } from '../../utils/format';
import { deriveModeFromEngines } from '../../utils/mode';

export function OverviewPage() {
  const { data: engines, isLoading: enginesLoading, error: enginesError } = useEnginesStatus();
  const { data: portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolioSummary();
  const { data: signals, isLoading: signalsLoading, error: signalsError } = useRecentSignals(10);
  const { data: today, isLoading: todayLoading, error: todayError } = useTodaySummary();
  const { data: analytics, isLoading: analyticsLoading, error: analyticsError } = useAnalyticsSummary();
  
  const tradingMode = deriveModeFromEngines(engines?.engines);
  
  // Prefer analytics summary as canonical source, fall back to portfolio/today
  const equityValue = analytics?.equity?.current_equity ?? portfolio?.equity ?? 0;
  const realizedPnl = analytics?.equity?.realized_pnl ?? today?.realized_pnl ?? 0;
  const unrealizedPnl = analytics?.equity?.unrealized_pnl ?? 0;
  const totalNotional = analytics?.equity?.total_notional ?? portfolio?.total_notional ?? 0;
  const totalTrades = analytics?.overall?.total_trades ?? today?.num_trades ?? 0;
  const winRate = analytics?.overall?.win_rate ?? today?.win_rate ?? 0;
  
  // Calculate daily P&L as sum of realized + unrealized (or from today if no analytics)
  const dailyPnl = (realizedPnl + unrealizedPnl) || today?.realized_pnl || 0;
  
  // Debug flag - set to true to see raw API data
  const DEBUG_MODE = import.meta.env.DEV || false; // Only in development
  
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
                    <span className={`font-bold uppercase ${
                      tradingMode === 'LIVE' ? 'text-negative' : 
                      tradingMode === 'PAPER' ? 'text-warning' : 
                      'text-text-secondary'
                    }`}>
                      {tradingMode}
                    </span>
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
        
        {/* Portfolio Snapshot - using analytics summary as canonical source */}
        {portfolioLoading || analyticsLoading ? (
          <CardSkeleton />
        ) : portfolioError && analyticsError ? (
          <CardError title="Portfolio" error={portfolioError || analyticsError} />
        ) : (
          <Card title="Portfolio">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Equity:</span>
                <span className="font-semibold">{formatCurrency(equityValue)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Daily P&L:</span>
                <span className={`font-semibold ${getPnlClass(dailyPnl)}`}>
                  {getPnlPrefix(dailyPnl)}{formatCurrency(dailyPnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Realized P&L:</span>
                <span className={`font-semibold ${getPnlClass(realizedPnl)}`}>
                  {getPnlPrefix(realizedPnl)}{formatCurrency(realizedPnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Unrealized P&L:</span>
                <span className={`font-semibold ${getPnlClass(unrealizedPnl)}`}>
                  {getPnlPrefix(unrealizedPnl)}{formatCurrency(unrealizedPnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Total Notional:</span>
                <span className="font-semibold">{formatCurrency(totalNotional)}</span>
              </div>
              {analytics?.status === 'stale' && (
                <div className="text-xs text-warning">⚠ Data may be stale</div>
              )}
              {analytics?.status === 'empty' && (
                <div className="text-xs text-text-secondary">ℹ No data yet</div>
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
                <span className="text-text-secondary">Trades:</span>
                <span className="font-semibold">{totalTrades}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary">Win Rate:</span>
                <span className="font-semibold">{formatPercent(winRate)}</span>
              </div>
              {analytics?.overall && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-text-secondary">Win/Loss:</span>
                    <span className="font-semibold text-sm">
                      {analytics.overall.win_trades}/{analytics.overall.loss_trades}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-text-secondary">Profit Factor:</span>
                    <span className="font-semibold">{analytics.overall.profit_factor.toFixed(2)}</span>
                  </div>
                </>
              )}
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
                {formatCurrency(Math.abs(Math.min(0, realizedPnl)))}
              </span>
            </div>
            <div className="w-full bg-border rounded-full h-2 mt-2">
              <div 
                className="bg-warning rounded-full h-2 transition-all"
                style={{ 
                  width: `${Math.min(100, Math.abs(Math.min(0, realizedPnl)) / 3000 * 100)}%` 
                }}
              ></div>
            </div>
          </div>
        </Card>
      </div>
      
      {/* DEBUG: Raw API Data (Development Only) */}
      {DEBUG_MODE && analytics && (
        <Card title="🔍 DEBUG: Analytics Summary API Response">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              This debug block shows raw API data from <code className="bg-border px-1 rounded">/api/analytics/summary</code>
            </div>
            <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
              {JSON.stringify(analytics, null, 2)}
            </pre>
            <div className="text-text-secondary text-[10px] mt-2">
              ✓ Data is being fetched and updated every 5 seconds<br/>
              Status: <strong>{analytics.status}</strong><br/>
              {analytics.equity ? '✓ Equity data is present' : '⚠️ Equity is null/missing'}<br/>
              {analytics.overall ? '✓ Overall metrics present' : '⚠️ Overall metrics missing'}
            </div>
          </div>
        </Card>
      )}
      
      {DEBUG_MODE && portfolio && (
        <Card title="🔍 DEBUG: Portfolio API Response (legacy)">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              Legacy endpoint data from <code className="bg-border px-1 rounded">/api/portfolio/summary</code>
            </div>
            <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
              {JSON.stringify(portfolio, null, 2)}
            </pre>
          </div>
        </Card>
      )}
      
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
