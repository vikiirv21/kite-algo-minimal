/**
 * Main Dashboard Bootstrap
 * Entry point for Arthayukti HFT Dashboard
 * 
 * Features:
 * - Tab switching with state preservation
 * - Real-time data polling with smart re-rendering
 * - Color-coded P&L values
 * - Auto-scroll logs with follow mode
 * - Responsive design
 */

import * as API from './api_client.js';
import { initState, setState, getState, deriveMode } from './state.js';
import { initTabs, renderTab } from './tabs.js';
import { formatTime } from './components/index.js';

// Polling intervals (milliseconds)
const INTERVALS = {
  time: 1000,           // 1s - Server time
  engines: 2000,        // 2s - Engine status
  portfolio: 2000,      // 2s - Portfolio
  positions: 3000,      // 3s - Open positions
  positionsClosed: 5000, // 5s - Closed positions (slower update)
  orders: 3000,         // 3s - Orders
  signals: 2000,        // 2s - Signals
  logs: 3000,           // 3s - Logs
  analytics: 3000,      // 3s - Analytics (updated from 10s)
  config: 30000,        // 30s - Config (slow changing)
};

// Polling timers
const timers = {};

/**
 * Initialize the dashboard
 */
async function init() {
  console.log('🚀 Initializing Arthayukti Dashboard...');
  
  // Initialize state
  initState();
  
  // Initialize tabs
  initTabs();
  
  // Render initial tab
  renderTab('overview');
  
  // Start polling loops
  startPolling();
  
  // Initial data fetch
  await fetchAll();
  
  console.log('✅ Dashboard initialized');
}

/**
 * Fetch all data (initial load)
 */
async function fetchAll() {
  try {
    await Promise.all([
      fetchTime(),
      fetchMeta(),
      fetchConfig(),
      fetchEngines(),
      fetchPortfolio(),
      fetchTodaySummary(),
      fetchPositions(),
      fetchClosedPositions(),
      fetchOrders(),
      fetchSignals(),
      fetchLogs(),
    ]);
  } catch (error) {
    console.error('Error fetching initial data:', error);
  }
}

/**
 * Start all polling loops
 */
function startPolling() {
  timers.time = setInterval(fetchTime, INTERVALS.time);
  timers.engines = setInterval(fetchEngines, INTERVALS.engines);
  timers.portfolio = setInterval(fetchPortfolio, INTERVALS.portfolio);
  timers.positions = setInterval(fetchPositions, INTERVALS.positions);
  timers.positionsClosed = setInterval(fetchClosedPositions, INTERVALS.positionsClosed);
  timers.orders = setInterval(fetchOrders, INTERVALS.orders);
  timers.signals = setInterval(fetchSignals, INTERVALS.signals);
  timers.logs = setInterval(fetchLogs, INTERVALS.logs);
  timers.analytics = setInterval(fetchAnalytics, INTERVALS.analytics);
  timers.config = setInterval(fetchConfig, INTERVALS.config);
  
  console.log('⏱️ Polling started');
}

/**
 * Stop all polling loops
 */
function stopPolling() {
  Object.values(timers).forEach(timer => clearInterval(timer));
  console.log('⏹️ Polling stopped');
}

// ========== Fetch Functions ==========

async function fetchTime() {
  try {
    const data = await API.getTime();
    updateServerTime(data.utc);
  } catch (error) {
    console.error('Error fetching time:', error);
  }
}

async function fetchMeta() {
  try {
    const data = await API.getMeta();
    setState({ 
      marketOpen: data.market_open,
      marketStatus: data.market_status 
    });
    updateMarketStatus(data);
  } catch (error) {
    console.error('Error fetching meta:', error);
  }
}

async function fetchConfig() {
  try {
    const data = await API.getConfig();
    setState({ config: data });
  } catch (error) {
    console.error('Error fetching config:', error);
  }
}

async function fetchEngines() {
  try {
    const data = await API.getEnginesStatus();
    const engines = data.engines || [];
    const mode = deriveMode(engines);
    
    setState({ engines, mode });
    updateModeDisplay(mode);
    updateConnectionStatus('ok');
    
    // Re-render current tab if needed
    const state = getState();
    if (state.activeTab === 'overview') {
      renderTab('overview');
    }
  } catch (error) {
    console.error('Error fetching engines:', error);
    updateConnectionStatus('error');
  }
}

async function fetchPortfolio() {
  try {
    const data = await API.getPortfolioSnapshot();
    setState({ portfolioSnapshot: data });
    
    // Re-render if on portfolio or overview tab
    const state = getState();
    if (state.activeTab === 'overview' || state.activeTab === 'portfolio') {
      renderTab(state.activeTab);
    }
  } catch (error) {
    console.error('Error fetching portfolio:', error);
  }
}

async function fetchTodaySummary() {
  try {
    const data = await API.getTodaySummary();
    setState({ todaySummary: data });
  } catch (error) {
    console.error('Error fetching today summary:', error);
  }
}

async function fetchPositions() {
  try {
    const data = await API.getOpenPositions();
    setState({ positionsOpen: data || [] });
    
    // Re-render if on portfolio tab
    const state = getState();
    if (state.activeTab === 'portfolio') {
      renderTab('portfolio');
    }
  } catch (error) {
    console.error('Error fetching positions:', error);
  }
}

async function fetchClosedPositions() {
  try {
    const data = await API.getClosedPositions(20);
    setState({ positionsClosed: Array.isArray(data) ? data : [] });
    
    // Re-render if on portfolio tab
    const state = getState();
    if (state.activeTab === 'portfolio') {
      renderTab('portfolio');
    }
  } catch (error) {
    // Closed positions endpoint may not exist - fail silently
    // console.error('Error fetching closed positions:', error);
    setState({ positionsClosed: [] });
  }
}

async function fetchOrders() {
  try {
    const data = await API.getOrders(50);
    setState({ orders: Array.isArray(data) ? data : [] });
    
    // Re-render if on trading tab
    const state = getState();
    if (state.activeTab === 'trading') {
      renderTab('trading');
    }
  } catch (error) {
    console.error('Error fetching orders:', error);
  }
}

async function fetchSignals() {
  try {
    const data = await API.getSignals(50);
    setState({ signals: Array.isArray(data) ? data : [] });
    
    // Re-render if on signals or overview tab
    const state = getState();
    if (state.activeTab === 'signals' || state.activeTab === 'overview') {
      renderTab(state.activeTab);
    }
  } catch (error) {
    console.error('Error fetching signals:', error);
  }
}

async function fetchLogs() {
  try {
    const data = await API.getLogs({ limit: 150 });
    const logs = data.logs || data.entries || [];
    setState({ logs });
    
    // Re-render if on logs tab
    const state = getState();
    if (state.activeTab === 'logs') {
      renderTab('logs');
      
      // Auto-scroll if follow is enabled
      const followCheckbox = document.getElementById('log-follow');
      const logsDisplay = document.getElementById('logs-display');
      if (followCheckbox?.checked && logsDisplay) {
        logsDisplay.scrollTop = logsDisplay.scrollHeight;
      }
    }
  } catch (error) {
    console.error('Error fetching logs:', error);
  }
}

async function fetchAnalytics() {
  try {
    const [equityCurve, analyticsSummary] = await Promise.all([
      API.getEquityCurve(1),
      API.getAnalyticsSummary().catch(() => null),
    ]);
    
    setState({ 
      equityCurve: equityCurve?.equity_curve || [],
      analyticsSummary 
    });
    
    // Re-render if on analytics or overview tab (since overview shows PnL data)
    const state = getState();
    if (state.activeTab === 'analytics' || state.activeTab === 'overview') {
      renderTab(state.activeTab);
    }
  } catch (error) {
    console.error('Error fetching analytics:', error);
  }
}

// ========== UI Update Functions ==========

function updateServerTime(utcTime) {
  const timeEl = document.getElementById('server-time');
  if (timeEl && utcTime) {
    timeEl.textContent = formatTime(utcTime);
  }
}

function updateModeDisplay(mode) {
  const modeBadge = document.getElementById('mode-badge');
  const modeText = document.getElementById('mode-text');
  
  if (modeBadge) {
    modeBadge.dataset.mode = mode;
  }
  
  if (modeText) {
    modeText.textContent = mode;
  }
}

function updateMarketStatus(data) {
  // Can be used to update market status indicators if needed
  // For now, mode badge is sufficient
}

function updateConnectionStatus(status) {
  const statusDot = document.querySelector('.status-dot');
  if (statusDot) {
    statusDot.dataset.status = status;
  }
  
  setState({ connectionStatus: status });
}

// ========== Event Listeners ==========

// Handle visibility change to pause/resume polling
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    console.log('⏸️ Page hidden, stopping polling');
    stopPolling();
  } else {
    console.log('▶️ Page visible, resuming polling');
    startPolling();
    fetchAll();
  }
});

// Handle page unload
window.addEventListener('beforeunload', () => {
  stopPolling();
});

// ========== Start Application ==========

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
