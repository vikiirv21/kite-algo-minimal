import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

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
  });
}

export function usePortfolioSummary() {
  return useQuery({
    queryKey: queryKeys.portfolio,
    queryFn: api.getPortfolioSummary,
    refetchInterval: 3000, // 3 seconds
  });
}

export function useOpenPositions() {
  return useQuery({
    queryKey: queryKeys.positions,
    queryFn: api.getOpenPositions,
    refetchInterval: 3000, // 3 seconds
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
  });
}

export function useStrategyStats(days = 1) {
  return useQuery({
    queryKey: queryKeys.strategies(days),
    queryFn: () => api.getStrategyStats(days),
    refetchInterval: 10000, // 10 seconds
  });
}

export function useEquityCurve(days = 1) {
  return useQuery({
    queryKey: queryKeys.equityCurve(days),
    queryFn: () => api.getEquityCurve(days),
    refetchInterval: 10000, // 10 seconds
  });
}

export function useTodaySummary() {
  return useQuery({
    queryKey: queryKeys.todaySummary,
    queryFn: api.getTodaySummary,
    refetchInterval: 5000, // 5 seconds
  });
}

export function useLogs(params?: { limit?: number; level?: string; contains?: string; kind?: string }) {
  return useQuery({
    queryKey: queryKeys.logs(params),
    queryFn: () => api.getLogs(params),
    refetchInterval: 2000, // 2 seconds
  });
}
