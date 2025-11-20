import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api } from '../api/client';

/**
 * React Query hooks for Dashboard API endpoints.
 * 
 * Hook → Endpoint mapping:
 * - useMeta() → /api/meta
 * - useConfigSummary() → /api/config/summary
 * - useAuthStatus() → /api/auth/status
 * - useEnginesStatus() → /api/engines/status
 * - usePortfolioSummary() → /api/portfolio/summary
 * - useOpenPositions() → /api/positions/open
 * - useOrders(limit) → /api/orders?limit={limit}
 * - useRecentOrders(limit) → /api/orders/recent?limit={limit}
 * - useSignals(limit) → /api/signals?limit={limit}
 * - useRecentSignals(limit) → /api/signals/recent?limit={limit}
 * - useStrategyStats(days) → /api/stats/strategies?days={days}
 * - useEquityCurve(days) → /api/stats/equity?days={days}
 * - useTodaySummary() → /api/summary/today
 * - useLogs(params) → /api/logs?{params}
 * - useSystemTime() → /api/system/time
 * - useAnalyticsSummary() → /api/analytics/summary
 * - useAnalyticsEquityCurve(params) → /api/analytics/equity_curve?{params}
 * - useRiskSummary() → /api/risk/summary
 * 
 * All hooks use React Query with appropriate refetchInterval for live updates.
 * See docs/api_dashboard_mapping.md for complete mapping documentation.
 */

// Query keys
export const queryKeys = {
  meta: ['meta'] as const,
  config: ['config'] as const,
  auth: ['auth'] as const,
  engines: ['engines'] as const,
  portfolio: ['portfolio'] as const,
  positions: ['positions'] as const,
  orders: (limit: number) => ['orders', limit] as const,
  recentOrders: (limit: number) => ['orders', 'recent', limit] as const,
  signals: (limit: number) => ['signals', limit] as const,
  recentSignals: (limit: number) => ['signals', 'recent', limit] as const,
  strategies: (days: number) => ['strategies', days] as const,
  equityCurve: (days: number) => ['equity', days] as const,
  todaySummary: ['today'] as const,
  logs: (params?: { limit?: number; level?: string; contains?: string; kind?: string }) => ['logs', params] as const,
};

// Hooks with appropriate refetch intervals
export function useMeta() {
  return useQuery({
    queryKey: queryKeys.meta,
    queryFn: api.getMeta,
    refetchInterval: 2000, // 2 seconds
  });
}

export function useConfigSummary() {
  return useQuery({
    queryKey: queryKeys.config,
    queryFn: api.getConfigSummary,
  });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: queryKeys.auth,
    queryFn: api.getAuthStatus,
    refetchInterval: 60000, // 1 minute
  });
}

export function useEnginesStatus() {
  return useQuery({
    queryKey: queryKeys.engines,
    queryFn: api.getEnginesStatus,
    refetchInterval: 3000, // 3 seconds
    refetchIntervalInBackground: true,
  });
}

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio', 'full'] as const,
    queryFn: api.getPortfolio,
    refetchInterval: 2000, // 2 seconds - live portfolio updates
    refetchIntervalInBackground: true,
  });
}

export function usePortfolioSummary() {
  return useQuery({
    queryKey: queryKeys.portfolio,
    queryFn: api.getPortfolioSummary,
    refetchInterval: 2000, // 2 seconds - portfolio metrics need to be most responsive
    refetchIntervalInBackground: true,
  });
}

export function useOpenPositions() {
  return useQuery({
    queryKey: queryKeys.positions,
    queryFn: api.getOpenPositions,
    refetchInterval: 3000, // 3 seconds
    refetchIntervalInBackground: true,
  });
}

export function useOrders(limit = 150) {
  return useQuery({
    queryKey: queryKeys.orders(limit),
    queryFn: () => api.getOrders(limit),
    refetchInterval: 5000, // 5 seconds
  });
}

export function useRecentOrders(limit = 50) {
  return useQuery({
    queryKey: queryKeys.recentOrders(limit),
    queryFn: () => api.getRecentOrders(limit),
    refetchInterval: 3000, // 3 seconds
    refetchIntervalInBackground: true,
  });
}

export function useSignals(limit = 150) {
  return useQuery({
    queryKey: queryKeys.signals(limit),
    queryFn: () => api.getSignals(limit),
    refetchInterval: 5000, // 5 seconds
  });
}

export function useRecentSignals(limit = 50) {
  return useQuery({
    queryKey: queryKeys.recentSignals(limit),
    queryFn: () => api.getRecentSignals(limit),
    refetchInterval: 2000, // 2 seconds
    refetchIntervalInBackground: true,
  });
}

export function useStrategyStats(days = 1) {
  return useQuery({
    queryKey: queryKeys.strategies(days),
    queryFn: () => api.getStrategyStats(days),
    refetchInterval: 5000, // 5 seconds
  });
}

export function useEquityCurve(days = 1) {
  return useQuery({
    queryKey: queryKeys.equityCurve(days),
    queryFn: () => api.getEquityCurve(days),
    refetchInterval: 5000, // 5 seconds
  });
}

export function useTodaySummary() {
  return useQuery({
    queryKey: queryKeys.todaySummary,
    queryFn: api.getTodaySummary,
    refetchInterval: 3000, // 3 seconds
    refetchIntervalInBackground: true,
  });
}

export function useLogs(params?: { limit?: number; level?: string; contains?: string; kind?: string }) {
  return useQuery({
    queryKey: queryKeys.logs(params),
    queryFn: () => api.getLogs(params),
    refetchInterval: 2000, // 2 seconds for polling
  });
}

export function useSystemTime() {
  return useQuery({
    queryKey: ['systemTime'] as const,
    queryFn: api.getSystemTime,
    refetchInterval: 1000, // 1 second
  });
}

// Derived hook for connection status
export function useConnectionStatus() {
  const query = useSystemTime();
  const { isSuccess, isError, dataUpdatedAt } = query;
  
  return useMemo(() => {
    // eslint-disable-next-line react-hooks/purity -- Date.now() required for time-based status calculation
    const timeSinceUpdate = dataUpdatedAt > 0 ? Date.now() - dataUpdatedAt : Infinity;
    
    // Consider disconnected if no update in 15 seconds
    const isConnected = isSuccess && timeSinceUpdate < 15000;
    
    return {
      isConnected,
      isDisconnected: isError || timeSinceUpdate >= 15000,
      timeSinceUpdate,
    };
  }, [isSuccess, isError, dataUpdatedAt]);
}

// Analytics hooks
export function useAnalyticsSummary() {
  return useQuery({
    queryKey: ['analytics', 'summary'] as const,
    queryFn: api.getAnalyticsSummary,
    refetchInterval: 5000, // 5 seconds for responsive updates
    refetchIntervalInBackground: true,
  });
}

export function useAnalyticsEquityCurve(params?: { strategy?: string; symbol?: string }) {
  return useQuery({
    queryKey: ['analytics', 'equity_curve', params] as const,
    queryFn: () => api.getAnalyticsEquityCurve(params),
    refetchInterval: 10000, // 10 seconds
  });
}

// Risk hook
export function useRiskSummary() {
  return useQuery({
    queryKey: ['risk', 'summary'] as const,
    queryFn: api.getRiskSummary,
    refetchInterval: 5000, // 5 seconds
  });
}

// Engine Logs hook
export function useEngineLogs(engine: string, lines = 200, enabled = true) {
  return useQuery({
    queryKey: ['engine-logs', engine, lines] as const,
    queryFn: () => api.getEngineLogs(engine, lines),
    refetchInterval: 2000, // 2 seconds
    enabled, // Only fetch when enabled (active tab)
  });
}

// Strategy Lab hooks
export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'] as const,
    queryFn: api.getStrategies,
    refetchInterval: 5000, // 5 seconds
  });
}

// Advanced Risk hooks
export function useRiskLimits() {
  return useQuery({
    queryKey: ['risk', 'limits'] as const,
    queryFn: api.getRiskLimits,
    refetchInterval: 10000, // 10 seconds
  });
}

export function useRiskBreaches() {
  return useQuery({
    queryKey: ['risk', 'breaches'] as const,
    queryFn: api.getRiskBreaches,
    refetchInterval: 5000, // 5 seconds - check frequently for breaches
  });
}

export function useVaR(horizonDays = 1, confidence = 0.95) {
  return useQuery({
    queryKey: ['risk', 'var', horizonDays, confidence] as const,
    queryFn: () => api.getVaR(horizonDays, confidence),
    refetchInterval: 30000, // 30 seconds - VaR doesn't change rapidly
  });
}

// Performance Metrics hook
export function useMetrics() {
  return useQuery({
    queryKey: ['pm', 'metrics'] as const,
    queryFn: api.getMetrics,
    refetchInterval: 5000, // 5 seconds
    refetchIntervalInBackground: true,
  });
}

// Trading Status hook
export function useTradingStatus() {
  return useQuery({
    queryKey: ['trading', 'status'] as const,
    queryFn: api.getTradingStatus,
    refetchInterval: 3000, // 3 seconds
    refetchIntervalInBackground: true,
  });
}
