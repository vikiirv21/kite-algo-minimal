import { Card, CardSkeleton } from '../../components/Card';
import { useEquityCurve } from '../../hooks/useApi';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

export function AnalyticsPage() {
  const { data: equityCurve, isLoading } = useEquityCurve();
  
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
      
      {/* Equity Curve */}
      <Card title="Equity Curve">
        {isLoading ? (
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
      
      {/* Per-Strategy Performance Placeholder */}
      <Card title="Strategy Performance">
        <div className="text-center text-text-secondary py-12">
          <p className="font-semibold">Strategy Performance Metrics Coming Soon</p>
          <p className="text-sm mt-2">
            To enable this feature, add the following API endpoint:
          </p>
          <pre className="mt-4 text-left inline-block bg-surface-light p-4 rounded text-xs">
{`GET /api/analytics/strategies
Returns:
[
  {
    strategy: "ema_crossover",
    pnl: 5000,
    win_rate: 65.5,
    max_drawdown: -1200,
    avg_trade_pnl: 150,
    ...
  },
  ...
]`}
          </pre>
        </div>
      </Card>
    </div>
  );
}
