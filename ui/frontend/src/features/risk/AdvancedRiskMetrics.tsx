import { Card, CardSkeleton } from '../../components/Card';
import { useRiskLimits, useRiskBreaches, useVaR } from '../../hooks/useApi';
import { formatCurrency, formatPercent } from '../../utils/format';

export function AdvancedRiskMetrics() {
  const { data: limits, isLoading: limitsLoading } = useRiskLimits();
  const { data: breaches, isLoading: breachesLoading } = useRiskBreaches();
  const { data: varData, isLoading: varLoading } = useVaR(1, 0.95);

  if (limitsLoading || breachesLoading || varLoading) {
    return <CardSkeleton />;
  }

  const criticalBreaches = breaches?.filter(b => b.severity === 'critical') || [];
  const warningBreaches = breaches?.filter(b => b.severity === 'warning') || [];

  return (
    <Card title="Advanced Risk Metrics">
      {/* Risk Breaches Alert */}
      {breaches && breaches.length > 0 && (
        <div className="mb-6">
          <div className="font-semibold mb-3 text-text">Active Risk Breaches</div>
          <div className="space-y-2">
            {criticalBreaches.map((breach, idx) => (
              <div key={idx} className="bg-negative/20 border border-negative/50 rounded-lg px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">🚨</span>
                  <div className="flex-1">
                    <div className="font-semibold text-negative">{breach.code}</div>
                    <div className="text-sm text-text-secondary">{breach.message}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-negative">
                      {breach.metric.current.toFixed(2)} {breach.metric.unit}
                    </div>
                    <div className="text-xs text-text-secondary">
                      Limit: {breach.metric.limit.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            {warningBreaches.map((breach, idx) => (
              <div key={idx} className="bg-warning/20 border border-warning/50 rounded-lg px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">⚠️</span>
                  <div className="flex-1">
                    <div className="font-semibold text-warning">{breach.code}</div>
                    <div className="text-sm text-text-secondary">{breach.message}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-warning">
                      {breach.metric.current.toFixed(2)} {breach.metric.unit}
                    </div>
                    <div className="text-xs text-text-secondary">
                      Limit: {breach.metric.limit.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Risk Limits Configuration */}
      <div className="mb-6">
        <div className="font-semibold mb-3 text-text">Risk Limits Configuration</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface-light rounded-lg p-4">
            <div className="text-sm text-text-secondary mb-1">Max Daily Loss</div>
            <div className="text-xl font-bold">{formatCurrency(limits?.max_daily_loss_rupees || 0)}</div>
            <div className="text-xs text-text-secondary mt-1">
              Rupees lost before trading halts
            </div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="text-sm text-text-secondary mb-1">Max Daily Drawdown</div>
            <div className="text-xl font-bold">
              {formatPercent((limits?.max_daily_drawdown_pct || 0) * 100)}
            </div>
            <div className="text-xs text-text-secondary mt-1">
              Percentage drawdown limit
            </div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="text-sm text-text-secondary mb-1">Max Trades/Day</div>
            <div className="text-xl font-bold">{limits?.max_trades_per_day || 0}</div>
            <div className="text-xs text-text-secondary mt-1">
              Global daily trade limit
            </div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="text-sm text-text-secondary mb-1">Max Trades/Symbol</div>
            <div className="text-xl font-bold">{limits?.max_trades_per_symbol_per_day || 0}</div>
            <div className="text-xs text-text-secondary mt-1">
              Per-symbol daily trade limit
            </div>
          </div>
        </div>
      </div>

      {/* Value at Risk */}
      <div className="mb-6">
        <div className="font-semibold mb-3 text-text">Value at Risk (VaR)</div>
        <div className="bg-surface-light rounded-lg p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-sm text-text-secondary mb-1">VaR (Rupees)</div>
              <div className="text-2xl font-bold text-warning">
                {formatCurrency(varData?.var_rupees || 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">VaR (Percentage)</div>
              <div className="text-2xl font-bold text-warning">
                {formatPercent(varData?.var_pct || 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-text-secondary mb-1">Method</div>
              <div className="text-lg font-semibold">{varData?.method || 'historical'}</div>
              <div className="text-xs text-text-secondary mt-1">
                {varData?.confidence ? `${(varData.confidence * 100).toFixed(0)}% confidence` : '95% confidence'}
              </div>
            </div>
          </div>
          <div className="mt-3 text-xs text-text-secondary">
            Based on {varData?.sample_size || 0} historical days. 
            VaR represents the maximum expected loss at the {varData?.confidence ? (varData.confidence * 100).toFixed(0) : '95'}% confidence level.
          </div>
        </div>
      </div>

      {/* Additional Risk Features */}
      <div>
        <div className="font-semibold mb-3 text-text">Additional Risk Controls</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface-light rounded-lg p-4">
            <div className="font-semibold text-sm mb-2">📊 Max Drawdown Monitoring</div>
            <div className="text-xs text-text-secondary">
              Tracks largest peak-to-trough decline and enforces stop-loss limits
            </div>
            <div className="mt-2 text-xs text-positive">✓ Active</div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="font-semibold text-sm mb-2">🎯 Per-Symbol Position Limits</div>
            <div className="text-xs text-text-secondary">
              Controls concentration risk by limiting exposure per instrument
            </div>
            <div className="mt-2 text-xs text-positive">✓ Active</div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="font-semibold text-sm mb-2">🔗 Loss Streak Protection</div>
            <div className="text-xs text-text-secondary">
              Halts trading after {limits?.max_loss_streak || 5} consecutive losses
            </div>
            <div className="mt-2 text-xs text-positive">✓ Active</div>
          </div>
          <div className="bg-surface-light rounded-lg p-4">
            <div className="font-semibold text-sm mb-2">⚡ Statistical Risk Assessment</div>
            <div className="text-xs text-text-secondary">
              Historical VaR provides probabilistic risk estimates
            </div>
            <div className="mt-2 text-xs text-positive">✓ Active</div>
          </div>
        </div>
      </div>

      {/* No Breaches State */}
      {(!breaches || breaches.length === 0) && (
        <div className="mt-6 bg-positive/10 border border-positive/30 rounded-lg px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-xl">✓</span>
            <div className="font-semibold text-positive">
              All risk limits within safe thresholds
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
