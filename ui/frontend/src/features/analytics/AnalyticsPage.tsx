import { Card, CardSkeleton } from '../../components/Card';
import { useEquityCurve, useAnalyticsSummary } from '../../hooks/useApi';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { formatCurrency, getPnlClass, getPnlPrefix } from '../../utils/format';

export function AnalyticsPage() {
  const { data: equityCurve, isLoading: equityCurveLoading } = useEquityCurve();
  const { data: analytics, isLoading: analyticsLoading } = useAnalyticsSummary();
  
  // Format data for charts
  const chartData = equityCurve?.map(point => ({
    time: new Date(point.ts).toLocaleTimeString('en-IN', { 
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'Asia/Kolkata'
    }),
    equity: point.equity,
    realized: point.realized,
    unrealized: point.unrealized,
  })) || [];
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Analytics</h1>
      
      {/* Daily Analytics Summary */}
      {analyticsLoading ? (
        <CardSkeleton />
      ) : analytics?.daily ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card title="Today's P&L">
            <div className={`text-3xl font-bold ${getPnlClass(analytics.daily.realized_pnl)}`}>
              {getPnlPrefix(analytics.daily.realized_pnl)}{formatCurrency(analytics.daily.realized_pnl)}
            </div>
            <div className="text-sm text-text-secondary mt-2">
              {analytics.daily.num_trades} trades
            </div>
          </Card>
          
          <Card title="Win Rate">
            <div className="text-3xl font-bold">
              {analytics.daily.win_rate.toFixed(1)}%
            </div>
            <div className="text-sm text-text-secondary mt-2">
              W: {analytics.daily.pnl_distribution.wins} / L: {analytics.daily.pnl_distribution.losses}
            </div>
          </Card>
          
          <Card title="Avg Win / Loss">
            <div className="space-y-1">
              <div className={`text-lg font-semibold ${getPnlClass(analytics.daily.avg_win)}`}>
                Win: {formatCurrency(analytics.daily.avg_win)}
              </div>
              <div className={`text-lg font-semibold ${getPnlClass(analytics.daily.avg_loss)}`}>
                Loss: {formatCurrency(analytics.daily.avg_loss)}
              </div>
            </div>
          </Card>
          
          <Card title="Best / Worst">
            <div className="space-y-1">
              <div className={`text-lg font-semibold ${getPnlClass(analytics.daily.biggest_winner)}`}>
                Best: {formatCurrency(analytics.daily.biggest_winner)}
              </div>
              <div className={`text-lg font-semibold ${getPnlClass(analytics.daily.biggest_loser)}`}>
                Worst: {formatCurrency(analytics.daily.biggest_loser)}
              </div>
            </div>
          </Card>
        </div>
      ) : null}
      
      {/* Equity Curve */}
      <Card title="Equity Curve">
        {equityCurveLoading ? (
          <CardSkeleton />
        ) : chartData.length === 0 ? (
          <div className="text-center text-text-secondary py-12">
            <p>No equity data available yet.</p>
            <p className="text-sm mt-2">Equity curve will appear once trading begins.</p>
          </div>
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3447" />
                <XAxis 
                  dataKey="time" 
                  stroke="#6b7280" 
                  style={{ fontSize: '12px' }}
                />
                <YAxis 
                  stroke="#6b7280" 
                  style={{ fontSize: '12px' }}
                  tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#121825', 
                    border: '1px solid #2a3447',
                    borderRadius: '4px'
                  }}
                  formatter={(value: number) => [`₹${value.toFixed(2)}`, '']}
                />
                <Legend />
                <Line 
                  type="monotone" 
                  dataKey="equity" 
                  stroke="#3b82f6" 
                  strokeWidth={2}
                  name="Equity"
                  dot={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="realized" 
                  stroke="#10b981" 
                  strokeWidth={1}
                  strokeDasharray="5 5"
                  name="Realized"
                  dot={false}
                />
                <Line 
                  type="monotone" 
                  dataKey="unrealized" 
                  stroke="#f59e0b" 
                  strokeWidth={1}
                  strokeDasharray="5 5"
                  name="Unrealized"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
      
      {/* Per-Strategy Performance */}
      {analytics?.strategies && Object.keys(analytics.strategies).length > 0 ? (
        <Card title="Strategy Performance">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-text-secondary font-medium">Strategy</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">P&L</th>
                  <th className="pb-2 text-text-secondary font-medium text-center">Trades</th>
                  <th className="pb-2 text-text-secondary font-medium text-center">Win Rate</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(analytics.strategies).map(([strategy, data]) => (
                  <tr key={strategy} className="border-b border-border/50 hover:bg-surface-light">
                    <td className="py-3 font-medium">{strategy}</td>
                    <td className={`py-3 text-right font-mono ${getPnlClass(data.pnl)}`}>
                      {getPnlPrefix(data.pnl)}{formatCurrency(data.pnl)}
                    </td>
                    <td className="py-3 text-center font-mono">{data.trades}</td>
                    <td className="py-3 text-center font-mono">{data.win_rate.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
      
      {/* Per-Symbol Performance */}
      {analytics?.symbols && Object.keys(analytics.symbols).length > 0 ? (
        <Card title="Symbol Performance">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                  <th className="pb-2 text-text-secondary font-medium text-right">P&L</th>
                  <th className="pb-2 text-text-secondary font-medium text-center">Trades</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(analytics.symbols).map(([symbol, data]) => (
                  <tr key={symbol} className="border-b border-border/50 hover:bg-surface-light">
                    <td className="py-3 font-medium">{symbol}</td>
                    <td className={`py-3 text-right font-mono ${getPnlClass(data.pnl)}`}>
                      {getPnlPrefix(data.pnl)}{formatCurrency(data.pnl)}
                    </td>
                    <td className="py-3 text-center font-mono">{data.trades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
      
      {/* Benchmarks Placeholder */}
      <Card title="Benchmarks">
        <div className="text-center text-text-secondary py-12">
          <p className="font-semibold">Benchmark Comparison Coming Soon</p>
          <p className="text-sm mt-2">
            To enable this feature, add the following API endpoint:
          </p>
          <pre className="mt-4 text-left inline-block bg-surface-light p-4 rounded text-xs">
{`GET /api/benchmarks
Returns:
[
  { ts: "2024-11-17T10:00:00+00:00", nifty: 19500, banknifty: 45000 },
  ...
]`}
          </pre>
        </div>
      </Card>
    </div>
  );
}
