import { Card, CardSkeleton } from '../../components/Card';
import { usePortfolioSummary, useOpenPositions } from '../../hooks/useApi';
import { formatCurrency, formatPercent, getPnlClass, getPnlPrefix } from '../../utils/format';

export function PortfolioPage() {
  const { data: portfolio, isLoading: portfolioLoading } = usePortfolioSummary();
  const { data: positions, isLoading: positionsLoading } = useOpenPositions();
  
  // Debug flag - set to true to see raw API data
  const DEBUG_MODE = import.meta.env.DEV || false; // Only in development
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Portfolio</h1>
      
      {/* Portfolio Summary */}
      {portfolioLoading ? (
        <CardSkeleton />
      ) : (
        <Card title="Portfolio Summary">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <div className="text-sm text-text-secondary mb-1">Equity</div>
              <div className="text-2xl font-bold">{formatCurrency(portfolio?.equity)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Daily P&L</div>
              <div className={`text-2xl font-bold ${getPnlClass(portfolio?.daily_pnl)}`}>
                {getPnlPrefix(portfolio?.daily_pnl)}{formatCurrency(portfolio?.daily_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Realized P&L</div>
              <div className={`text-2xl font-bold ${getPnlClass(portfolio?.total_realized_pnl)}`}>
                {getPnlPrefix(portfolio?.total_realized_pnl)}{formatCurrency(portfolio?.total_realized_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Unrealized P&L</div>
              <div className={`text-2xl font-bold ${getPnlClass(portfolio?.total_unrealized_pnl)}`}>
                {getPnlPrefix(portfolio?.total_unrealized_pnl)}{formatCurrency(portfolio?.total_unrealized_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Total Notional</div>
              <div className="text-lg font-semibold">{formatCurrency(portfolio?.total_notional)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Free Margin</div>
              <div className="text-lg font-semibold">{formatCurrency(portfolio?.free_notional)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Exposure</div>
              <div className="text-lg font-semibold">
                {(portfolio?.exposure_pct !== null && portfolio?.exposure_pct !== undefined) 
                  ? formatPercent(portfolio.exposure_pct * 100) 
                  : '--'}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Positions</div>
              <div className="text-lg font-semibold">{portfolio?.position_count || 0}</div>
            </div>
          </div>
        </Card>
      )}
      
      {/* DEBUG: Raw API Data (Development Only) */}
      {DEBUG_MODE && (
        <Card title="🔍 DEBUG: Portfolio Summary API Response">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              Raw API data from <code className="bg-border px-1 rounded">/api/portfolio/summary</code>
            </div>
            <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
              {JSON.stringify(portfolio, null, 2)}
            </pre>
          </div>
        </Card>
      )}
      
      {DEBUG_MODE && positions && positions.length > 0 && (
        <Card title="🔍 DEBUG: Open Positions API Response (First 2)">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              Raw API data from <code className="bg-border px-1 rounded">/api/positions/open</code>
            </div>
            <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
              {JSON.stringify(positions.slice(0, 2), null, 2)}
            </pre>
            <div className="text-text-secondary text-[10px] mt-2">
              ✓ Showing first 2 positions out of {positions.length} total<br/>
              ✓ Data updates every 3 seconds
            </div>
          </div>
        </Card>
      )}
      
      {/* Open Positions */}
      <Card title="Open Positions">
        {positionsLoading ? (
          <div className="space-y-2">
            <div className="h-4 bg-border rounded animate-pulse"></div>
            <div className="h-4 bg-border rounded animate-pulse"></div>
          </div>
        ) : !positions || positions.length === 0 ? (
          <div className="text-center text-text-secondary py-8">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                  <th className="pb-2 text-text-secondary font-medium">Side</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Quantity</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">Avg Price</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">LTP</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">P&L</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => {
                  const pnlPct = pos.avg_price > 0 
                    ? (pos.unrealized_pnl / (pos.avg_price * Math.abs(pos.quantity))) * 100 
                    : 0;
                  
                  return (
                    <tr key={idx} className="border-b border-border/50 hover:bg-surface-light">
                      <td className="py-3 font-medium">{pos.symbol}</td>
                      <td className="py-3">
                        <span className={`
                          px-2 py-1 rounded text-xs font-semibold
                          ${pos.side === 'LONG' ? 'bg-positive/20 text-positive' : 'bg-negative/20 text-negative'}
                        `}>
                          {pos.side}
                        </span>
                      </td>
                      <td className="py-3 text-right font-mono">{Math.abs(pos.quantity)}</td>
                      <td className="py-3 text-right font-mono">{formatCurrency(pos.avg_price)}</td>
                      <td className="py-3 text-right font-mono">{formatCurrency(pos.last_price)}</td>
                      <td className={`py-3 text-right font-mono font-semibold ${getPnlClass(pos.unrealized_pnl)}`}>
                        {getPnlPrefix(pos.unrealized_pnl)}{formatCurrency(pos.unrealized_pnl)}
                      </td>
                      <td className={`py-3 text-right font-mono ${getPnlClass(pos.unrealized_pnl)}`}>
                        {getPnlPrefix(pnlPct)}{formatPercent(Math.abs(pnlPct))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
