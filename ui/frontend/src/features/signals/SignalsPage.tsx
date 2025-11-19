import { Card, CardSkeleton, CardError } from '../../components/Card';
import { useStrategyStats, useRecentSignals } from '../../hooks/useApi';
import { formatTimestamp } from '../../utils/format';
import { StrategyLab } from './StrategyLab';

export function SignalsPage() {
  const { data: strategies, isLoading: strategiesLoading, error: strategiesError } = useStrategyStats();
  const { data: signals, isLoading: signalsLoading, error: signalsError } = useRecentSignals(50);
  
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Signals</h1>
      
      {/* Strategies */}
      {strategiesError ? (
        <CardError title="Active Strategies" error={strategiesError} />
      ) : strategiesLoading ? (
        <CardSkeleton />
      ) : (
        <Card title="Active Strategies">
          {!strategies || strategies.length === 0 ? (
            <div className="text-center text-text-secondary py-8">No strategies configured</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-left">
                    <th className="pb-2 text-text-secondary font-medium">Strategy</th>
                    <th className="pb-2 text-text-secondary font-medium">Symbol</th>
                    <th className="pb-2 text-text-secondary font-medium">Timeframe</th>
                    <th className="pb-2 text-text-secondary font-medium">Mode</th>
                    <th className="pb-2 text-text-secondary font-medium text-center">Signals Today</th>
                    <th className="pb-2 text-text-secondary font-medium text-center">Win Rate</th>
                    <th className="pb-2 text-text-secondary font-medium">Last Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.map((strat, idx) => (
                    <tr key={idx} className="border-b border-border/50 hover:bg-surface-light">
                      <td className="py-3 font-medium">{strat.strategy || strat.logical}</td>
                      <td className="py-3">{strat.symbol}</td>
                      <td className="py-3 text-sm">{strat.timeframe}</td>
                      <td className="py-3">
                        <span className={`
                          px-2 py-1 rounded text-xs font-semibold uppercase
                          ${strat.mode === 'paper' ? 'bg-warning/20 text-warning' : 'bg-primary/20 text-primary'}
                        `}>
                          {strat.mode}
                        </span>
                      </td>
                      <td className="py-3 text-center font-mono">
                        {strat.buy_count + strat.sell_count + strat.exit_count}
                      </td>
                      <td className="py-3 text-center font-mono">
                        {strat.winrate_20 ? `${strat.winrate_20.toFixed(1)}%` : '--'}
                      </td>
                      <td className="py-3 text-sm">
                        <span className={`
                          px-2 py-1 rounded text-xs font-semibold
                          ${strat.last_signal === 'BUY' ? 'bg-positive/20 text-positive' : 
                            strat.last_signal === 'SELL' ? 'bg-negative/20 text-negative' : 
                            'bg-muted/20 text-muted'}
                        `}>
                          {strat.last_signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
      
      {/* Strategy Lab */}
      <StrategyLab />
      
      {/* Signal Stream */}
      {signalsError ? (
        <CardError title="Signal Stream" error={signalsError} />
      ) : (
        <Card title="Signal Stream">
          {signalsLoading ? (
            <CardSkeleton />
          ) : !signals || signals.length === 0 ? (
            <div className="text-center text-text-secondary py-8">No signals yet</div>
          ) : (
            <div className="overflow-x-auto max-h-[600px] overflow-y-auto scrollbar-thin">
              <table className="w-full">
                <thead className="sticky top-0 bg-surface">
                  <tr className="border-b border-border text-left">
                    <th className="pb-2 pt-2 text-text-secondary font-medium">Time</th>
                    <th className="pb-2 pt-2 text-text-secondary font-medium">Symbol</th>
                    <th className="pb-2 pt-2 text-text-secondary font-medium">Direction</th>
                    <th className="pb-2 pt-2 text-text-secondary font-medium">Strategy</th>
                    <th className="pb-2 pt-2 text-text-secondary font-medium">TF</th>
                    <th className="pb-2 pt-2 text-text-secondary font-medium text-right">Price</th>
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
                      <td className="py-2 text-sm text-text-secondary">{signal.tf}</td>
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
