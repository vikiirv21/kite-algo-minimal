/**
 * API Client - Centralized API calls for Arthayukti Dashboard
 * All backend API calls are defined here with error handling
 */

const BASE_URL = '';  // Same origin

/**
 * Generic fetch with error handling
 */
async function fetchAPI(url, options = {}) {
  try {
    const response = await fetch(BASE_URL + url, options);
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    // Only log non-404 errors to reduce console noise
    if (!error.message.includes('404')) {
      console.error(`Failed to fetch ${url}:`, error);
    }
    throw error;
  }
}

// ========== System / Meta ==========

export async function getTime() {
  return fetchAPI('/api/system/time');
}

export async function getMeta() {
  return fetchAPI('/api/meta');
}

export async function getConfig() {
  return fetchAPI('/api/config/summary');
}

// ========== Auth ==========

export async function getAuthStatus() {
  return fetchAPI('/api/auth/status');
}

// ========== Engines ==========

export async function getEnginesStatus() {
  return fetchAPI('/api/engines/status');
}

// ========== Portfolio ==========

export async function getPortfolioSnapshot() {
  return fetchAPI('/api/portfolio/summary');
}

export async function getTodaySummary() {
  return fetchAPI('/api/summary/today');
}

// ========== Positions ==========

export async function getOpenPositions() {
  return fetchAPI('/api/positions/open');
}

export async function getClosedPositions(limit = 50) {
  return fetchAPI(`/api/positions/closed?limit=${limit}`);
}

// ========== Orders ==========

export async function getOrders(limit = 50) {
  return fetchAPI(`/api/orders?limit=${limit}`);
}

export async function getRecentOrders(limit = 20) {
  return fetchAPI(`/api/orders/recent?limit=${limit}`);
}

// ========== Signals ==========

export async function getSignals(limit = 50) {
  return fetchAPI(`/api/signals?limit=${limit}`);
}

export async function getRecentSignals(limit = 20) {
  return fetchAPI(`/api/signals/recent?limit=${limit}`);
}

// ========== Strategies ==========

export async function getStrategies() {
  return fetchAPI('/api/strategies');
}

export async function getStrategyStats(days = 1) {
  return fetchAPI(`/api/stats/strategies?days=${days}`);
}

// ========== Logs ==========

export async function getLogs(params = {}) {
  const { limit = 150, level, contains, kind } = params;
  const query = new URLSearchParams();
  query.append('limit', limit);
  if (level) query.append('level', level);
  if (contains) query.append('contains', contains);
  if (kind) query.append('kind', kind);
  
  return fetchAPI(`/api/logs?${query.toString()}`);
}

// ========== Analytics ==========

export async function getEquityCurve(days = 1) {
  return fetchAPI(`/api/stats/equity?days=${days}`);
}

export async function getAnalyticsSummary() {
  return fetchAPI('/api/analytics/summary');
}

export async function getBenchmarks() {
  // This endpoint may not exist yet - return placeholder
  return { error: 'Not implemented' };
}

export async function getStrategyPerf() {
  // This endpoint may not exist yet - return placeholder
  return { error: 'Not implemented' };
}

// ========== Health ==========

export async function getHealth() {
  return fetchAPI('/api/health');
}

export async function getQualitySummary() {
  return fetchAPI('/api/quality/summary');
}

export async function getTradeFlow() {
  return fetchAPI('/api/trade_flow');
}

// ========== Risk ==========

export async function getRiskSummary() {
  return fetchAPI('/api/risk/summary');
}
