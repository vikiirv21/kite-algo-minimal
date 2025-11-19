import type {
  MetaResponse,
  ConfigSummary,
  EnginesStatusResponse,
  PortfolioSummary,
  Signal,
  Order,
  Position,
  LogsResponse,
  StrategyStats,
  EquityCurvePoint,
  TodaySummary,
  AuthStatus,
  AnalyticsSummary,
  EquityCurveData,
  RiskSummary,
  EngineLogsTailResponse,
  Portfolio,
  StrategyDetail,
  BacktestRequest,
  BacktestResult,
  RiskLimits,
  RiskBreach,
  VaRResponse,
} from '../types/api';

const API_BASE = '/api';

async function fetchApi<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`);
  }
  return response.json();
}

export const api = {
  // Meta & System
  getMeta: () => fetchApi<MetaResponse>('/meta'),
  getConfigSummary: () => fetchApi<ConfigSummary>('/config/summary'),
  getSystemTime: () => fetchApi<{ utc: string }>('/system/time'),
  
  // Authentication
  getAuthStatus: () => fetchApi<AuthStatus>('/auth/status'),
  
  // Engines
  getEnginesStatus: () => fetchApi<EnginesStatusResponse>('/engines/status'),
  
  // Portfolio
  getPortfolio: () => fetchApi<Portfolio>('/portfolio'),
  getPortfolioSummary: () => fetchApi<PortfolioSummary>('/portfolio/summary'),
  getOpenPositions: () => fetchApi<Position[]>('/positions/open'),
  
  // Orders
  getOrders: (limit = 150) => fetchApi<Order[]>(`/orders?limit=${limit}`),
  getRecentOrders: (limit = 50) => fetchApi<{ orders: Order[] }>(`/orders/recent?limit=${limit}`),
  
  // Signals
  getSignals: (limit = 150) => fetchApi<Signal[]>(`/signals?limit=${limit}`),
  getRecentSignals: (limit = 50) => fetchApi<Signal[]>(`/signals/recent?limit=${limit}`),
  
  // Strategies
  getStrategyStats: (days = 1) => fetchApi<StrategyStats[]>(`/stats/strategies?days=${days}`),
  
  // Analytics
  getEquityCurve: (days = 1) => fetchApi<EquityCurvePoint[]>(`/stats/equity?days=${days}`),
  getTodaySummary: () => fetchApi<TodaySummary>('/summary/today'),
  
  // Logs
  getLogs: (params?: { limit?: number; level?: string; contains?: string; kind?: string }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.level) query.append('level', params.level);
    if (params?.contains) query.append('contains', params.contains);
    if (params?.kind) query.append('kind', params.kind);
    return fetchApi<LogsResponse>(`/logs?${query.toString()}`);
  },
  
  // Analytics
  getAnalyticsSummary: () => fetchApi<AnalyticsSummary>('/analytics/summary'),
  getAnalyticsEquityCurve: (params?: { strategy?: string; symbol?: string }) => {
    const query = new URLSearchParams();
    if (params?.strategy) query.append('strategy', params.strategy);
    if (params?.symbol) query.append('symbol', params.symbol);
    const queryStr = query.toString();
    return fetchApi<EquityCurveData>(`/analytics/equity_curve${queryStr ? '?' + queryStr : ''}`);
  },
  
  // Risk
  getRiskSummary: () => fetchApi<RiskSummary>('/risk/summary'),
  
  // Engine Logs
  getEngineLogs: (engine: string, lines = 200) => 
    fetchApi<EngineLogsTailResponse>(`/logs/tail?engine=${engine}&lines=${lines}`),
  
  // Strategy Lab APIs
  getStrategies: () => fetchApi<StrategyDetail[]>('/strategies'),
  enableStrategy: (strategyId: string): Promise<StrategyDetail> => 
    fetch(`${API_BASE}/strategies/${strategyId}/enable`, { method: 'POST' })
      .then(r => r.json()),
  disableStrategy: (strategyId: string): Promise<StrategyDetail> => 
    fetch(`${API_BASE}/strategies/${strategyId}/disable`, { method: 'POST' })
      .then(r => r.json()),
  updateStrategyParams: (strategyId: string, params: Record<string, any>): Promise<StrategyDetail> =>
    fetch(`${API_BASE}/strategies/${strategyId}/params`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ params }),
    }).then(r => r.json()),
  backtestStrategy: (strategyId: string, request: BacktestRequest): Promise<BacktestResult> =>
    fetch(`${API_BASE}/strategies/${strategyId}/backtest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }).then(r => r.json()),
  
  // Advanced Risk APIs
  getRiskLimits: () => fetchApi<RiskLimits>('/risk/limits'),
  updateRiskLimits: (limits: Partial<RiskLimits>): Promise<RiskLimits> =>
    fetch(`${API_BASE}/risk/limits`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(limits),
    }).then(r => r.json()),
  getRiskBreaches: () => fetchApi<RiskBreach[]>('/risk/breaches'),
  getVaR: (horizonDays = 1, confidence = 0.95) => 
    fetchApi<VaRResponse>(`/risk/var?horizon_days=${horizonDays}&confidence=${confidence}`),
};
