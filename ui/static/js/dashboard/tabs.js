/**
 * Tabs Controller - Handles tab switching and rendering
 */

import { getState } from './state.js';
import { createCard, createTable, createSkeletonLines, createMetricRow, 
         formatCurrency, formatNumber, formatPercent, formatTime, formatShortTime } from './components/index.js';

/**
 * Initialize tab switching
 */
export function initTabs() {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const tabName = tab.dataset.tab;
      switchTab(tabName);
    });
  });
}

/**
 * Switch to a tab
 */
export function switchTab(tabName) {
  // Update tab UI
  document.querySelectorAll('.tab').forEach(tab => {
    if (tab.dataset.tab === tabName) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });
  
  // Render tab content
  renderTab(tabName);
}

/**
 * Render a tab's content
 */
export function renderTab(tabName) {
  const content = document.getElementById('tab-content');
  
  switch (tabName) {
    case 'overview':
      content.innerHTML = '';
      content.appendChild(renderOverviewTab());
      break;
    case 'trading':
      content.innerHTML = '';
      content.appendChild(renderTradingTab());
      break;
    case 'portfolio':
      content.innerHTML = '';
      content.appendChild(renderPortfolioTab());
      break;
    case 'signals':
      content.innerHTML = '';
      content.appendChild(renderSignalsTab());
      break;
    case 'analytics':
      content.innerHTML = '';
      content.appendChild(renderAnalyticsTab());
      break;
    case 'system':
      content.innerHTML = '';
      content.appendChild(renderSystemTab());
      break;
    case 'logs':
      content.innerHTML = '';
      content.appendChild(renderLogsTab());
      break;
    default:
      content.innerHTML = '<div class="card"><div class="card-body">Tab not found</div></div>';
  }
}

/**
 * Overview Tab
 */
function renderOverviewTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-3';
  
  // Engine Status Card
  const engineCard = createCard('Engine Status', 
    state.engines.length > 0 ? `${state.engines.length} engine(s)` : '0 engines');
  const engineBody = document.createElement('div');
  engineBody.className = 'card-body';
  
  if (state.engines.length === 0) {
    engineBody.appendChild(createSkeletonLines(3));
  } else {
    state.engines.forEach(engine => {
      engineBody.appendChild(createMetricRow(
        engine.engine || 'Engine',
        engine.running ? '🟢 Running' : '🔴 Stopped'
      ));
    });
  }
  engineCard.querySelector('.card-body')?.remove();
  engineCard.appendChild(engineBody);
  
  // Portfolio Snapshot Card
  const portfolioCard = createCard('Portfolio Snapshot');
  const portfolioBody = document.createElement('div');
  portfolioBody.className = 'card-body';
  
  if (!state.portfolioSnapshot) {
    portfolioBody.appendChild(createSkeletonLines(5));
  } else {
    const p = state.portfolioSnapshot;
    portfolioBody.appendChild(createMetricRow('Equity', formatCurrency(p.equity)));
    portfolioBody.appendChild(createMetricRow('Realized P&L', formatCurrency(p.total_realized_pnl)));
    portfolioBody.appendChild(createMetricRow('Unrealized P&L', formatCurrency(p.total_unrealized_pnl)));
    portfolioBody.appendChild(createMetricRow('Daily P&L', formatCurrency(p.daily_pnl)));
    portfolioBody.appendChild(createMetricRow('Exposure', formatPercent(p.exposure_pct * 100)));
  }
  portfolioCard.querySelector('.card-body')?.remove();
  portfolioCard.appendChild(portfolioBody);
  
  // Recent Signals Card
  const signalsCard = createCard('Recent Signals', 
    state.signals.length > 0 ? `${state.signals.length} signals` : '0 signals');
  const signalsBody = document.createElement('div');
  signalsBody.className = 'card-body';
  
  if (state.signals.length === 0) {
    const emptyMsg = document.createElement('p');
    emptyMsg.className = 'text-muted text-sm text-center';
    emptyMsg.textContent = 'No signals yet';
    signalsBody.appendChild(emptyMsg);
  } else {
    const headers = ['Time', 'Symbol', 'Signal', 'Price', 'Strategy'];
    const rows = state.signals.slice(0, 5).map(s => [
      formatShortTime(s.ts),
      s.symbol || '—',
      s.signal || '—',
      formatCurrency(s.price, 2),
      s.strategy || '—'
    ]);
    signalsBody.appendChild(createTable(headers, rows));
  }
  signalsCard.querySelector('.card-body')?.remove();
  signalsCard.appendChild(signalsBody);
  
  container.appendChild(engineCard);
  container.appendChild(portfolioCard);
  container.appendChild(signalsCard);
  
  return container;
}

/**
 * Trading Tab
 */
function renderTradingTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-2';
  
  // Active Orders Card
  const ordersCard = createCard('Active Orders', 
    state.orders.length > 0 ? `${state.orders.length} orders` : '0 orders');
  const ordersBody = document.createElement('div');
  ordersBody.className = 'card-body';
  
  if (state.orders.length === 0) {
    const emptyMsg = document.createElement('p');
    emptyMsg.className = 'text-muted text-sm text-center';
    emptyMsg.textContent = 'No orders yet';
    ordersBody.appendChild(emptyMsg);
  } else {
    const headers = ['Time', 'Symbol', 'Side', 'Qty', 'Price', 'Status'];
    const rows = state.orders.slice(0, 20).map(o => [
      formatShortTime(o.timestamp || o.ts),
      o.symbol || '—',
      o.side || '—',
      o.quantity || o.qty || '—',
      formatCurrency(o.price, 2),
      o.status || '—'
    ]);
    ordersBody.appendChild(createTable(headers, rows));
  }
  ordersCard.querySelector('.card-body')?.remove();
  ordersCard.appendChild(ordersBody);
  
  container.appendChild(ordersCard);
  
  return container;
}

/**
 * Portfolio Tab
 */
function renderPortfolioTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-2';
  
  // Portfolio Summary Card
  const summaryCard = createCard('Portfolio Summary');
  const summaryBody = document.createElement('div');
  summaryBody.className = 'card-body';
  
  if (!state.portfolioSnapshot) {
    summaryBody.appendChild(createSkeletonLines(6));
  } else {
    const p = state.portfolioSnapshot;
    summaryBody.appendChild(createMetricRow('Paper Capital', formatCurrency(p.paper_capital)));
    summaryBody.appendChild(createMetricRow('Equity', formatCurrency(p.equity)));
    summaryBody.appendChild(createMetricRow('Total Notional', formatCurrency(p.total_notional)));
    summaryBody.appendChild(createMetricRow('Free Notional', formatCurrency(p.free_notional)));
    summaryBody.appendChild(createMetricRow('Realized P&L', formatCurrency(p.total_realized_pnl)));
    summaryBody.appendChild(createMetricRow('Unrealized P&L', formatCurrency(p.total_unrealized_pnl)));
  }
  summaryCard.querySelector('.card-body')?.remove();
  summaryCard.appendChild(summaryBody);
  
  // Open Positions Card
  const positionsCard = createCard('Open Positions',
    state.positionsOpen.length > 0 ? `${state.positionsOpen.length} positions` : '0 positions');
  const positionsBody = document.createElement('div');
  positionsBody.className = 'card-body';
  
  if (state.positionsOpen.length === 0) {
    const emptyMsg = document.createElement('p');
    emptyMsg.className = 'text-muted text-sm text-center';
    emptyMsg.textContent = 'No open positions';
    positionsBody.appendChild(emptyMsg);
  } else {
    const headers = ['Symbol', 'Side', 'Qty', 'Avg Price', 'LTP', 'P&L'];
    const rows = state.positionsOpen.map(pos => [
      pos.symbol || '—',
      pos.side || '—',
      pos.quantity || '—',
      formatCurrency(pos.avg_price, 2),
      formatCurrency(pos.last_price, 2),
      formatCurrency(pos.unrealized_pnl, 2)
    ]);
    positionsBody.appendChild(createTable(headers, rows));
  }
  positionsCard.querySelector('.card-body')?.remove();
  positionsCard.appendChild(positionsBody);
  
  container.appendChild(summaryCard);
  container.appendChild(positionsCard);
  
  return container;
}

/**
 * Signals Tab
 */
function renderSignalsTab() {
  const state = getState();
  const container = document.createElement('div');
  
  // Signals Card
  const signalsCard = createCard('All Signals', 
    state.signals.length > 0 ? `${state.signals.length} signals` : '0 signals');
  const signalsBody = document.createElement('div');
  signalsBody.className = 'card-body';
  
  if (state.signals.length === 0) {
    const emptyMsg = document.createElement('p');
    emptyMsg.className = 'text-muted text-sm text-center';
    emptyMsg.textContent = 'No signals yet';
    signalsBody.appendChild(emptyMsg);
  } else {
    const headers = ['Time', 'Symbol', 'TF', 'Signal', 'Price', 'Strategy'];
    const rows = state.signals.map(s => [
      formatTime(s.ts),
      s.symbol || '—',
      s.tf || '—',
      s.signal || '—',
      formatCurrency(s.price, 2),
      s.strategy || '—'
    ]);
    signalsBody.appendChild(createTable(headers, rows));
  }
  signalsCard.querySelector('.card-body')?.remove();
  signalsCard.appendChild(signalsBody);
  
  container.appendChild(signalsCard);
  
  return container;
}

/**
 * Analytics Tab
 */
function renderAnalyticsTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-3';
  
  // Today Summary Card
  const todayCard = createCard('Today at a Glance');
  const todayBody = document.createElement('div');
  todayBody.className = 'card-body';
  
  if (!state.todaySummary) {
    todayBody.appendChild(createSkeletonLines(4));
  } else {
    const t = state.todaySummary;
    todayBody.appendChild(createMetricRow('Realized P&L', formatCurrency(t.realized_pnl)));
    todayBody.appendChild(createMetricRow('Trades', t.num_trades || 0));
    todayBody.appendChild(createMetricRow('Win Rate', formatPercent(t.win_rate)));
    todayBody.appendChild(createMetricRow('Avg R', formatNumber(t.avg_r, 2)));
  }
  todayCard.querySelector('.card-body')?.remove();
  todayCard.appendChild(todayBody);
  
  // Equity Curve Placeholder
  const equityCard = createCard('Equity Curve');
  const equityBody = document.createElement('div');
  equityBody.className = 'card-body';
  equityBody.innerHTML = '<p class="text-muted text-sm text-center">Chart visualization will be added here</p>';
  equityCard.querySelector('.card-body')?.remove();
  equityCard.appendChild(equityBody);
  
  // Analytics Note
  const noteCard = createCard('Analytics Features');
  const noteBody = document.createElement('div');
  noteBody.className = 'card-body';
  noteBody.innerHTML = `
    <p class="text-sm">Advanced analytics features coming soon:</p>
    <ul class="text-sm text-muted" style="margin-left: var(--space-4); margin-top: var(--space-2);">
      <li>Equity curve visualization</li>
      <li>Benchmark comparison (NIFTY, BANKNIFTY)</li>
      <li>Per-strategy performance metrics</li>
      <li>Risk-adjusted returns</li>
    </ul>
  `;
  noteCard.querySelector('.card-body')?.remove();
  noteCard.appendChild(noteBody);
  
  container.appendChild(todayCard);
  container.appendChild(equityCard);
  container.appendChild(noteCard);
  
  return container;
}

/**
 * System Tab
 */
function renderSystemTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-2';
  
  // Config Card
  const configCard = createCard('Configuration');
  const configBody = document.createElement('div');
  configBody.className = 'card-body';
  
  if (!state.config) {
    configBody.appendChild(createSkeletonLines(5));
  } else {
    const c = state.config;
    configBody.appendChild(createMetricRow('Mode', c.mode || '—'));
    configBody.appendChild(createMetricRow('Paper Capital', formatCurrency(c.paper_capital)));
    configBody.appendChild(createMetricRow('Risk per Trade', formatPercent(c.risk_per_trade_pct * 100)));
    configBody.appendChild(createMetricRow('Max Daily Loss', formatCurrency(c.max_daily_loss)));
    configBody.appendChild(createMetricRow('Max Exposure', formatPercent(c.max_exposure_pct * 100)));
  }
  configCard.querySelector('.card-body')?.remove();
  configCard.appendChild(configBody);
  
  // System Info Card
  const systemCard = createCard('System Info');
  const systemBody = document.createElement('div');
  systemBody.className = 'card-body';
  systemBody.innerHTML = `
    <div class="metric-row">
      <span class="metric-label">Server Time</span>
      <span class="metric-value" id="system-server-time">—</span>
    </div>
    <div class="metric-row">
      <span class="metric-label">Market Status</span>
      <span class="metric-value" id="system-market-status">—</span>
    </div>
  `;
  systemCard.querySelector('.card-body')?.remove();
  systemCard.appendChild(systemBody);
  
  container.appendChild(configCard);
  container.appendChild(systemCard);
  
  return container;
}

/**
 * Logs Tab
 */
function renderLogsTab() {
  const state = getState();
  const container = document.createElement('div');
  
  // Logs Card
  const logsCard = createCard('Engine Logs', 
    state.logs.length > 0 ? `${state.logs.length} entries` : '0 entries');
  
  // Toolbar
  const toolbar = document.createElement('div');
  toolbar.className = 'card-body';
  toolbar.style.borderBottom = '1px solid var(--border-subtle)';
  toolbar.style.display = 'flex';
  toolbar.style.gap = 'var(--space-3)';
  toolbar.style.alignItems = 'center';
  
  const levelSelect = document.createElement('select');
  levelSelect.id = 'log-level-filter';
  levelSelect.style.padding = 'var(--space-2)';
  levelSelect.style.borderRadius = 'var(--radius-sm)';
  levelSelect.style.border = '1px solid var(--border-subtle)';
  levelSelect.style.backgroundColor = 'var(--bg-elevated)';
  levelSelect.style.color = 'var(--text-primary)';
  levelSelect.innerHTML = `
    <option value="">All Levels</option>
    <option value="INFO">INFO</option>
    <option value="WARNING">WARNING</option>
    <option value="ERROR">ERROR</option>
  `;
  
  const followLabel = document.createElement('label');
  followLabel.style.display = 'flex';
  followLabel.style.alignItems = 'center';
  followLabel.style.gap = 'var(--space-2)';
  followLabel.innerHTML = `
    <input type="checkbox" id="log-follow" checked>
    <span class="text-sm">Follow logs</span>
  `;
  
  toolbar.appendChild(levelSelect);
  toolbar.appendChild(followLabel);
  
  // Logs display
  const logsBody = document.createElement('div');
  logsBody.className = 'card-body';
  logsBody.style.maxHeight = '600px';
  logsBody.style.overflowY = 'auto';
  
  const logsPre = document.createElement('pre');
  logsPre.id = 'logs-display';
  logsPre.className = 'font-mono text-sm';
  logsPre.style.whiteSpace = 'pre-wrap';
  logsPre.style.margin = '0';
  
  if (state.logs.length === 0) {
    logsPre.textContent = 'No logs available';
  } else {
    logsPre.textContent = state.logs
      .map(log => `${log.timestamp || log.ts} [${log.level}] ${log.logger || log.source}: ${log.message}`)
      .join('\n');
  }
  
  logsBody.appendChild(logsPre);
  
  logsCard.querySelector('.card-body')?.remove();
  logsCard.appendChild(toolbar);
  logsCard.appendChild(logsBody);
  
  container.appendChild(logsCard);
  
  return container;
}
