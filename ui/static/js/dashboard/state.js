/**
 * State Management - Centralized state store for dashboard
 */

const state = {
  // Time & market
  serverTime: null,
  marketOpen: false,
  marketStatus: null,
  
  // Mode (derived from engines)
  mode: 'IDLE',
  
  // Engines
  engines: [],
  
  // Portfolio
  portfolioSnapshot: null,
  todaySummary: null,
  
  // Positions & Orders
  positionsOpen: [],
  positionsClosed: [],
  orders: [],
  
  // Signals & Strategies
  signals: [],
  strategies: [],
  
  // Logs
  logs: [],
  
  // Analytics
  equityCurve: [],
  analyticsSummary: null,
  
  // Health
  health: null,
  
  // Config
  config: null,
  
  // UI state
  activeTab: 'overview',
  connectionStatus: 'checking',
};

const listeners = new Set();

/**
 * Update state and notify listeners
 */
export function setState(updates) {
  Object.assign(state, updates);
  notifyListeners();
}

/**
 * Get current state
 */
export function getState() {
  return state;
}

/**
 * Subscribe to state changes
 */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Notify all listeners of state change
 */
function notifyListeners() {
  listeners.forEach(listener => {
    try {
      listener(state);
    } catch (error) {
      console.error('Listener error:', error);
    }
  });
}

/**
 * Initialize state with defaults
 */
export function initState() {
  setState({
    activeTab: 'overview',
    connectionStatus: 'checking',
  });
}

/**
 * Derive mode from engines status
 * If any live engine running → LIVE
 * Else if any paper engine running → PAPER
 * Else → IDLE
 */
export function deriveMode(engines) {
  if (!engines || engines.length === 0) return 'IDLE';
  
  const liveRunning = engines.some(e => e.mode === 'live' && e.running);
  const paperRunning = engines.some(e => e.mode === 'paper' && e.running);
  
  if (liveRunning) return 'LIVE';
  if (paperRunning) return 'PAPER';
  return 'IDLE';
}
