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
};
