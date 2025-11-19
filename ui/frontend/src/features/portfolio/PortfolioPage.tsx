import { Card, CardSkeleton } from '../../components/Card';
import { usePortfolio } from '../../hooks/useApi';
import { formatCurrency, formatPercent, getPnlClass, getPnlPrefix } from '../../utils/format';

export function PortfolioPage() {
  const { data: portfolio, isLoading: portfolioLoading } = usePortfolio();
  const positions = portfolio?.positions || [];
  const positionsLoading = portfolioLoading;
  
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
              <div className="text-sm text-text-secondary mb-1">Unrealized P&L</div>
              <div className={`text-2xl font-bold ${getPnlClass(portfolio?.unrealized_pnl)}`}>
                {getPnlPrefix(portfolio?.unrealized_pnl)}{formatCurrency(portfolio?.unrealized_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Realized P&L</div>
              <div className={`text-2xl font-bold ${getPnlClass(portfolio?.realized_pnl)}`}>
                {getPnlPrefix(portfolio?.realized_pnl)}{formatCurrency(portfolio?.realized_pnl)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Starting Capital</div>
              <div className="text-2xl font-bold">{formatCurrency(portfolio?.starting_capital)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Total Notional</div>
              <div className="text-lg font-semibold">{formatCurrency(portfolio?.total_notional)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Free Margin</div>
              <div className="text-lg font-semibold">{formatCurrency(portfolio?.free_margin)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Margin Used</div>
              <div className="text-lg font-semibold">{formatCurrency(portfolio?.margin_used)}</div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Positions</div>
              <div className="text-lg font-semibold">{positions.length}</div>
            </div>
          </div>
        </Card>
      )}
      
      {/* DEBUG: Raw API Data (Development Only) */}
      {DEBUG_MODE && (
        <Card title="🔍 DEBUG: Portfolio API Response">
          <div className="text-xs font-mono space-y-2">
            <div className="text-text-secondary mb-2">
              Raw API data from <code className="bg-border px-1 rounded">/api/portfolio</code> (updates every 2 seconds)
            </div>
            <pre className="bg-surface-light p-3 rounded overflow-x-auto text-[10px] leading-tight">
              {JSON.stringify(portfolio, null, 2)}
            </pre>
            <div className="text-text-secondary text-[10px] mt-2">
              ✓ Data is being fetched and updated every 2 seconds<br/>
              ✓ Includes live position data with real-time LTP and unrealized PnL
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
                  const pnlPct = pos.pnl_pct !== undefined ? pos.pnl_pct : 0;
                  
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
                      <td className="py-3 text-right font-mono">{pos.quantity}</td>
                      <td className="py-3 text-right font-mono">{formatCurrency(pos.avg_price)}</td>
                      <td className="py-3 text-right font-mono">{formatCurrency(pos.last_price)}</td>
                      <td className={`py-3 text-right font-mono font-semibold ${getPnlClass(pos.unrealized_pnl)}`}>
                        {getPnlPrefix(pos.unrealized_pnl)}{formatCurrency(pos.unrealized_pnl)}
                      </td>
                      <td className={`py-3 text-right font-mono ${getPnlClass(pnlPct)}`}>
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
