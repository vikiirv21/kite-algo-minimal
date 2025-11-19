import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Card } from '../../components/Card';
import { useStrategies } from '../../hooks/useApi';
import { api } from '../../api/client';
import type { StrategyDetail, BacktestRequest, BacktestResult } from '../../types/api';

export function StrategyLab() {
  const { data: strategies, isLoading } = useStrategies();
  const [editingStrategy, setEditingStrategy] = useState<StrategyDetail | null>(null);
  const [backtestingStrategy, setBacktestingStrategy] = useState<StrategyDetail | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const queryClient = useQueryClient();

  const enableMutation = useMutation({
    mutationFn: (strategyId: string) => api.enableStrategy(strategyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  const disableMutation = useMutation({
    mutationFn: (strategyId: string) => api.disableStrategy(strategyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  const updateParamsMutation = useMutation({
    mutationFn: ({ strategyId, params }: { strategyId: string; params: Record<string, any> }) =>
      api.updateStrategyParams(strategyId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
      setEditingStrategy(null);
    },
  });

  const backtestMutation = useMutation({
    mutationFn: ({ strategyId, request }: { strategyId: string; request: BacktestRequest }) =>
      api.backtestStrategy(strategyId, request),
    onSuccess: (data) => {
      setBacktestResult(data);
    },
  });

  const handleToggle = (strategy: StrategyDetail) => {
    if (strategy.enabled) {
      disableMutation.mutate(strategy.id);
    } else {
      enableMutation.mutate(strategy.id);
    }
  };

  if (isLoading) {
    return (
      <Card title="Strategy Lab">
        <div className="text-center text-text-secondary py-8">Loading strategies...</div>
      </Card>
    );
  }

  if (!strategies || strategies.length === 0) {
    return (
      <Card title="Strategy Lab">
        <div className="text-center text-text-secondary py-8">No strategies configured</div>
      </Card>
    );
  }

  return (
    <>
      <Card title="Strategy Lab">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="pb-2 text-text-secondary font-medium">Strategy</th>
                <th className="pb-2 text-text-secondary font-medium">Engine</th>
                <th className="pb-2 text-text-secondary font-medium">Timeframe</th>
                <th className="pb-2 text-text-secondary font-medium text-center">Status</th>
                <th className="pb-2 text-text-secondary font-medium text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((strategy) => (
                <tr key={strategy.id} className="border-b border-border/50 hover:bg-surface-light">
                  <td className="py-3">
                    <div className="font-medium">{strategy.name}</div>
                    <div className="text-xs text-text-secondary">{strategy.id}</div>
                  </td>
                  <td className="py-3">
                    <span className="px-2 py-1 rounded text-xs font-semibold uppercase bg-primary/20 text-primary">
                      {strategy.engine}
                    </span>
                  </td>
                  <td className="py-3 text-sm">{strategy.timeframe}</td>
                  <td className="py-3 text-center">
                    <button
                      onClick={() => handleToggle(strategy)}
                      disabled={enableMutation.isPending || disableMutation.isPending}
                      className={`
                        px-3 py-1 rounded text-xs font-semibold transition-colors
                        ${strategy.enabled
                          ? 'bg-positive/20 text-positive hover:bg-positive/30'
                          : 'bg-muted/20 text-muted hover:bg-muted/30'
                        }
                        disabled:opacity-50 disabled:cursor-not-allowed
                      `}
                    >
                      {strategy.enabled ? '✓ Enabled' : '○ Disabled'}
                    </button>
                  </td>
                  <td className="py-3 text-center">
                    <div className="flex gap-2 justify-center">
                      <button
                        onClick={() => setEditingStrategy(strategy)}
                        className="px-3 py-1 rounded text-xs font-semibold bg-surface-light hover:bg-border text-text transition-colors"
                      >
                        ⚙️ Params
                      </button>
                      <button
                        onClick={() => setBacktestingStrategy(strategy)}
                        className="px-3 py-1 rounded text-xs font-semibold bg-surface-light hover:bg-border text-text transition-colors"
                      >
                        📊 Backtest
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Parameters Editor Modal */}
      {editingStrategy && (
        <ParamsEditorModal
          strategy={editingStrategy}
          onClose={() => setEditingStrategy(null)}
          onSave={(params) => {
            updateParamsMutation.mutate({ strategyId: editingStrategy.id, params });
          }}
          isSaving={updateParamsMutation.isPending}
        />
      )}

      {/* Backtest Modal */}
      {backtestingStrategy && (
        <BacktestModal
          strategy={backtestingStrategy}
          onClose={() => {
            setBacktestingStrategy(null);
            setBacktestResult(null);
          }}
          onRun={(request) => {
            backtestMutation.mutate({ strategyId: backtestingStrategy.id, request });
          }}
          isRunning={backtestMutation.isPending}
          result={backtestResult}
        />
      )}
    </>
  );
}

// Parameters Editor Modal
function ParamsEditorModal({
  strategy,
  onClose,
  onSave,
  isSaving,
}: {
  strategy: StrategyDetail;
  onClose: () => void;
  onSave: (params: Record<string, any>) => void;
  isSaving: boolean;
}) {
  const [params, setParams] = useState(strategy.params);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surface rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-bold mb-4">Edit Parameters: {strategy.name}</h2>
        
        <div className="space-y-3">
          {Object.entries(params).map(([key, value]) => (
            <div key={key}>
              <label className="block text-sm font-medium text-text-secondary mb-1">
                {key}
              </label>
              <input
                type={typeof value === 'number' ? 'number' : 'text'}
                value={value}
                onChange={(e) => {
                  const newValue = typeof value === 'number' ? parseFloat(e.target.value) : e.target.value;
                  setParams({ ...params, [key]: newValue });
                }}
                className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          ))}
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={() => onSave(params)}
            disabled={isSaving}
            className="flex-1 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </button>
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 bg-surface-light text-text rounded-lg hover:bg-border disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// Backtest Modal
function BacktestModal({
  strategy,
  onClose,
  onRun,
  isRunning,
  result,
}: {
  strategy: StrategyDetail;
  onClose: () => void;
  onRun: (request: BacktestRequest) => void;
  isRunning: boolean;
  result: BacktestResult | null;
}) {
  const [symbol, setSymbol] = useState('SBIN');
  const [fromDate, setFromDate] = useState('2025-10-01');
  const [toDate, setToDate] = useState('2025-11-19');

  const handleRun = () => {
    onRun({
      symbol,
      engine: strategy.engine,
      timeframe: strategy.timeframe,
      from_date: fromDate,
      to_date: toDate,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surface rounded-lg p-6 max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-xl font-bold mb-4">Backtest: {strategy.name}</h2>

        {!result ? (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">Symbol</label>
              <input
                type="text"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="e.g., SBIN, HDFCBANK"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">From Date</label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1">To Date</label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="w-full px-3 py-2 bg-surface-light border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleRun}
                disabled={isRunning}
                className="flex-1 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed font-semibold"
              >
                {isRunning ? 'Running...' : '🚀 Run Backtest'}
              </button>
              <button
                onClick={onClose}
                disabled={isRunning}
                className="px-4 py-2 bg-surface-light text-text rounded-lg hover:bg-border disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-surface-light rounded-lg p-4">
              <h3 className="font-semibold mb-3">Results Summary</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <div className="text-sm text-text-secondary">Total Trades</div>
                  <div className="text-xl font-bold">{result.summary.trades}</div>
                </div>
                <div>
                  <div className="text-sm text-text-secondary">Win Rate</div>
                  <div className="text-xl font-bold">{(result.summary.win_rate * 100).toFixed(1)}%</div>
                </div>
                <div>
                  <div className="text-sm text-text-secondary">Total P&L</div>
                  <div className={`text-xl font-bold ${result.summary.total_pnl >= 0 ? 'text-positive' : 'text-negative'}`}>
                    ₹{result.summary.total_pnl.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-text-secondary">Max Drawdown</div>
                  <div className="text-xl font-bold text-negative">{result.summary.max_drawdown_pct.toFixed(2)}%</div>
                </div>
                {result.summary.avg_pnl_per_trade && (
                  <div>
                    <div className="text-sm text-text-secondary">Avg P&L/Trade</div>
                    <div className="text-xl font-bold">₹{result.summary.avg_pnl_per_trade.toFixed(2)}</div>
                  </div>
                )}
              </div>
            </div>

            {result.equity_curve && result.equity_curve.length > 0 && (
              <div className="bg-surface-light rounded-lg p-4">
                <h3 className="font-semibold mb-3">Equity Curve</h3>
                <div className="text-sm text-text-secondary">
                  {result.equity_curve.length} data points
                </div>
                {/* Simple text display for now - could add chart later */}
                <div className="mt-2 text-xs text-text-secondary">
                  Starting: ₹{result.equity_curve[0][1].toFixed(2)} → 
                  Ending: ₹{result.equity_curve[result.equity_curve.length - 1][1].toFixed(2)}
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => setSymbol('')}
                className="flex-1 px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 font-semibold"
              >
                Run Another
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-surface-light text-text rounded-lg hover:bg-border"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
