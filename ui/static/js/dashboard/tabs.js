/**
 * Tabs Controller - Handles tab switching and rendering
 * 
 * Key features:
 * - Tab switching with state persistence
 * - Color-coded P&L values (green for positive, red for negative)
 * - Timestamps on all data rows
 * - Auto-scroll logs with follow mode
 */

import { getState, setState } from './state.js';
import { createCard, createTable, createSkeletonLines, createMetricRow, 
         formatCurrency, formatNumber, formatPercent, formatTime, formatShortTime, formatDateTime,
         coloredPnL, coloredPercent, directionBadge } from './components/index.js';

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
  // Update state - this is critical so polling functions don't override the tab
  setState({ activeTab: tabName });
  
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
  
  // Prefer analytics summary data if available, fallback to portfolioSnapshot
  const analytics = state.analyticsSummary;
  const portfolio = state.portfolioSnapshot;
  
  if (!analytics && !portfolio) {
    portfolioBody.appendChild(createSkeletonLines(5));
  } else {
    // Use analytics data preferentially
    const equity = analytics?.equity || analytics?.current_equity || portfolio?.equity || 0;
    const realizedPnL = analytics?.realized_pnl || portfolio?.total_realized_pnl || 0;
    const unrealizedPnL = analytics?.unrealized_pnl || portfolio?.total_unrealized_pnl || 0;
    const dailyPnL = analytics?.daily_pnl || portfolio?.daily_pnl || (realizedPnL + unrealizedPnL);
    const openPositions = analytics?.open_positions_count || portfolio?.active_positions || 0;
    
    // Helper to create colored metric row
    const createColoredMetricRow = (label, value) => {
      const row = document.createElement('div');
      row.className = 'metric-row';
      
      const labelEl = document.createElement('span');
      labelEl.className = 'metric-label';
      labelEl.textContent = label;
      
      const valueEl = document.createElement('span');
      valueEl.className = 'metric-value';
      
      // Determine color class
      let colorClass = '';
      if (value > 0) colorClass = 'value-positive';
      else if (value < 0) colorClass = 'value-negative';
      
      if (colorClass) {
        valueEl.className += ' ' + colorClass;
      }
      valueEl.textContent = formatCurrency(value);
      
      row.appendChild(labelEl);
      row.appendChild(valueEl);
      return row;
    };
    
    portfolioBody.appendChild(createMetricRow('Equity', formatCurrency(equity)));
    portfolioBody.appendChild(createColoredMetricRow('Daily P&L', dailyPnL));
    portfolioBody.appendChild(createColoredMetricRow('Realized P&L', realizedPnL));
    portfolioBody.appendChild(createColoredMetricRow('Unrealized P&L', unrealizedPnL));
    portfolioBody.appendChild(createMetricRow('Open Positions', openPositions));
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
    const headers = ['Time', 'Symbol', 'Direction', 'Price', 'Strategy'];
    const rows = state.signals.slice(0, 5).map(s => [
      formatShortTime(s.ts || s.timestamp),
      s.symbol || '—',
      directionBadge(s.signal || s.direction),
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
 * Trading Tab - Shows recent orders with timestamps
 */
function renderTradingTab() {
  const state = getState();
  const container = document.createElement('div');
  container.className = 'grid grid-2';
  
  // Recent Orders Card
  const ordersCard = createCard('Recent Orders', 
    state.orders.length > 0 ? `${state.orders.length} orders` : '0 orders');
  const ordersBody = document.createElement('div');
  ordersBody.className = 'card-body';
  
  if (state.orders.length === 0) {
    const emptyMsg = document.createElement('p');
    emptyMsg.className = 'text-muted text-sm text-center';
    emptyMsg.textContent = 'No orders yet';
    ordersBody.appendChild(emptyMsg);
  } else {
    const headers = ['Time', 'Symbol', 'Side', 'Qty', 'Price', 'Status', 'Order ID'];
    const rows = state.orders.slice(0, 20).map(o => [
      formatShortTime(o.timestamp || o.ts || o.order_time),
      o.symbol || '—',
      directionBadge(o.side || o.transaction_type),
      o.quantity || o.qty || '—',
      formatCurrency(o.price, 2),
      o.status || '—',
      (o.order_id || o.id || '').toString().substring(0, 8) || '—'
    ]);
    ordersBody.appendChild(createTable(headers, rows));
  }
  ordersCard.querySelector('.card-body')?.remove();
  ordersCard.appendChild(ordersBody);
  
  container.appendChild(ordersCard);
  
  return container;
}

/**
 * Portfolio Tab - Shows portfolio summary, open positions, and closed positions with color-coded P&L
 */
function renderPortfolioTab() {
  const state = getState();
  const container = document.createElement('div');
  
  // Use full-width layout for portfolio
  const summaryRow = document.createElement('div');
  summaryRow.className = 'grid grid-2';
  
  // Portfolio Summary Card
  const summaryCard = createCard('Portfolio Summary');
  const summaryBody = document.createElement('div');
  summaryBody.className = 'card-body';
  
  if (!state.portfolioSnapshot) {
    summaryBody.appendChild(createSkeletonLines(6));
  } else {
    const p = state.portfolioSnapshot;
    
    // Helper to create colored metric row
    const createColoredMetricRow = (label, value) => {
      const row = document.createElement('div');
      row.className = 'metric-row';
      
      const labelEl = document.createElement('span');
      labelEl.className = 'metric-label';
      labelEl.textContent = label;
      
      const valueEl = document.createElement('span');
      valueEl.className = 'metric-value';
      
      // Determine color class
      let colorClass = '';
      if (value > 0) colorClass = 'value-positive';
      else if (value < 0) colorClass = 'value-negative';
      
      if (colorClass) {
        valueEl.className += ' ' + colorClass;
      }
      valueEl.textContent = formatCurrency(value);
      
      row.appendChild(labelEl);
      row.appendChild(valueEl);
      return row;
    };
    
    summaryBody.appendChild(createMetricRow('Paper Capital', formatCurrency(p.paper_capital)));
    summaryBody.appendChild(createMetricRow('Equity', formatCurrency(p.equity)));
    summaryBody.appendChild(createMetricRow('Total Notional', formatCurrency(p.total_notional)));
    summaryBody.appendChild(createMetricRow('Free Notional', formatCurrency(p.free_notional)));
    summaryBody.appendChild(createColoredMetricRow('Realized P&L', p.total_realized_pnl));
    summaryBody.appendChild(createColoredMetricRow('Unrealized P&L', p.total_unrealized_pnl));
  }
  summaryCard.querySelector('.card-body')?.remove();
  summaryCard.appendChild(summaryBody);
  
  summaryRow.appendChild(summaryCard);
  
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
    const headers = ['Symbol', 'Side', 'Qty', 'Avg Price', 'LTP', 'P&L', '%P&L'];
    const rows = state.positionsOpen.map(pos => [
      pos.symbol || '—',
      directionBadge(pos.side),
      pos.quantity || '—',
      formatCurrency(pos.avg_price, 2),
      formatCurrency(pos.last_price, 2),
      coloredPnL(pos.unrealized_pnl, 2),
      coloredPercent(pos.pnl_percent || 0, 2)
    ]);
    positionsBody.appendChild(createTable(headers, rows));
  }
  positionsCard.querySelector('.card-body')?.remove();
  positionsCard.appendChild(positionsBody);
  
  summaryRow.appendChild(positionsCard);
  container.appendChild(summaryRow);
  
  // Closed Positions Card (full width)
  if (state.positionsClosed && state.positionsClosed.length > 0) {
    const closedCard = createCard('Closed Positions', `${state.positionsClosed.length} closed`);
    const closedBody = document.createElement('div');
    closedBody.className = 'card-body';
    
    const headers = ['Closed Time', 'Symbol', 'Side', 'Qty', 'Entry Price', 'Exit Price', 'P&L', '%P&L'];
    const rows = state.positionsClosed.slice(0, 20).map(pos => [
      formatShortTime(pos.closed_at || pos.exit_time || pos.timestamp),
      pos.symbol || '—',
      directionBadge(pos.side),
      pos.quantity || '—',
      formatCurrency(pos.avg_entry_price || pos.avg_price, 2),
      formatCurrency(pos.avg_exit_price || pos.exit_price, 2),
      coloredPnL(pos.realized_pnl || pos.pnl, 2),
      coloredPercent(pos.pnl_percent || 0, 2)
    ]);
    closedBody.appendChild(createTable(headers, rows));
    closedCard.querySelector('.card-body')?.remove();
    closedCard.appendChild(closedBody);
    
    container.appendChild(closedCard);
  }
  
  return container;
}

/**
 * Signals Tab - Shows all signals with timestamps and direction badges
 */
function renderSignalsTab() {
  const state = getState();
  const container = document.createElement('div');
  
  // Signals Card (full width)
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
    const headers = ['Time', 'Symbol', 'TF', 'Direction', 'Price', 'Strategy', 'Confidence'];
    const rows = state.signals.map(s => [
      formatTime(s.ts || s.timestamp),
      s.symbol || '—',
      s.tf || s.timeframe || '—',
      directionBadge(s.signal || s.direction),
      formatCurrency(s.price, 2),
      s.strategy || '—',
      s.confidence ? formatPercent(s.confidence * 100, 1) : (s.score ? formatNumber(s.score, 2) : '—')
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
  
  const analytics = state.analyticsSummary;
  
  // Overall Metrics Card
  const overallCard = createCard('Overall Performance');
  const overallBody = document.createElement('div');
  overallBody.className = 'card-body';
  
  if (!analytics) {
    overallBody.appendChild(createSkeletonLines(6));
  } else {
    const overall = analytics.overall || {};
    const createColoredRow = (label, value) => {
      const row = document.createElement('div');
      row.className = 'metric-row';
      const labelEl = document.createElement('span');
      labelEl.className = 'metric-label';
      labelEl.textContent = label;
      const valueEl = document.createElement('span');
      valueEl.className = 'metric-value';
      if (value > 0) valueEl.className += ' value-positive';
      else if (value < 0) valueEl.className += ' value-negative';
      valueEl.textContent = formatCurrency(value);
      row.appendChild(labelEl);
      row.appendChild(valueEl);
      return row;
    };
    
    overallBody.appendChild(createColoredRow('Net P&L', overall.net_pnl || 0));
    overallBody.appendChild(createMetricRow('Total Trades', overall.total_trades || 0));
    overallBody.appendChild(createMetricRow('Win Rate', formatPercent((overall.win_rate || 0) * 100)));
    overallBody.appendChild(createMetricRow('Profit Factor', formatNumber(overall.profit_factor || 0, 2)));
    overallBody.appendChild(createColoredRow('Biggest Win', overall.biggest_win || 0));
    overallBody.appendChild(createColoredRow('Biggest Loss', overall.biggest_loss || 0));
  }
  overallCard.querySelector('.card-body')?.remove();
  overallCard.appendChild(overallBody);
  
  // Equity Curve Card
  const equityCard = createCard('Equity Curve');
  const equityBody = document.createElement('div');
  equityBody.className = 'card-body';
  
  if (!state.equityCurve || state.equityCurve.length === 0) {
    equityBody.innerHTML = '<p class="text-muted text-sm text-center">No equity data yet</p>';
  } else {
    // Simple text representation of equity curve (chart library can be added later)
    const latest = state.equityCurve[state.equityCurve.length - 1];
    const earliest = state.equityCurve[0];
    const change = latest?.equity - earliest?.equity || 0;
    const changePct = earliest?.equity ? (change / earliest?.equity) * 100 : 0;
    
    equityBody.appendChild(createMetricRow('Current', formatCurrency(latest?.equity || 0)));
    equityBody.appendChild(createMetricRow('Starting', formatCurrency(earliest?.equity || 0)));
    
    const changeRow = document.createElement('div');
    changeRow.className = 'metric-row';
    const changeLabel = document.createElement('span');
    changeLabel.className = 'metric-label';
    changeLabel.textContent = 'Change';
    const changeValue = document.createElement('span');
    changeValue.className = 'metric-value';
    if (change > 0) changeValue.className += ' value-positive';
    else if (change < 0) changeValue.className += ' value-negative';
    changeValue.textContent = `${formatCurrency(change)} (${formatPercent(changePct)})`;
    changeRow.appendChild(changeLabel);
    changeRow.appendChild(changeValue);
    equityBody.appendChild(changeRow);
    
    equityBody.appendChild(createMetricRow('Data Points', state.equityCurve.length));
  }
  equityCard.querySelector('.card-body')?.remove();
  equityCard.appendChild(equityBody);
  
  // Drawdown Card
  const drawdownCard = createCard('Risk Metrics');
  const drawdownBody = document.createElement('div');
  drawdownBody.className = 'card-body';
  
  if (!analytics) {
    drawdownBody.appendChild(createSkeletonLines(3));
  } else {
    drawdownBody.appendChild(createMetricRow('Max Equity', formatCurrency(analytics.max_equity || 0)));
    drawdownBody.appendChild(createMetricRow('Min Equity', formatCurrency(analytics.min_equity || 0)));
    
    const ddRow = document.createElement('div');
    ddRow.className = 'metric-row';
    const ddLabel = document.createElement('span');
    ddLabel.className = 'metric-label';
    ddLabel.textContent = 'Max Drawdown';
    const ddValue = document.createElement('span');
    ddValue.className = 'metric-value value-negative';
    ddValue.textContent = formatCurrency(analytics.max_drawdown || 0);
    ddRow.appendChild(ddLabel);
    ddRow.appendChild(ddValue);
    drawdownBody.appendChild(ddRow);
  }
  drawdownCard.querySelector('.card-body')?.remove();
  drawdownCard.appendChild(drawdownBody);
  
  container.appendChild(overallCard);
  container.appendChild(equityCard);
  container.appendChild(drawdownCard);
  
  // Add full-width cards for symbol and strategy breakdowns
  const fullWidthContainer = document.createElement('div');
  fullWidthContainer.style.gridColumn = '1 / -1';
  
  // Per-Symbol P&L Card
  const symbolCard = createCard('P&L by Symbol');
  const symbolBody = document.createElement('div');
  symbolBody.className = 'card-body';
  
  if (!analytics || !analytics.pnl_per_symbol || Object.keys(analytics.pnl_per_symbol).length === 0) {
    symbolBody.innerHTML = '<p class="text-muted text-sm text-center">No symbol data yet</p>';
  } else {
    const headers = ['Symbol', 'Realized P&L', 'Unrealized P&L', 'Total P&L', 'Trades', 'Win Rate'];
    const rows = Object.entries(analytics.pnl_per_symbol).map(([symbol, data]) => {
      const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : 0;
      return [
        symbol,
        coloredPnL(data.realized_pnl || 0),
        coloredPnL(data.unrealized_pnl || 0),
        coloredPnL(data.total_pnl || 0),
        data.trades || 0,
        formatPercent(winRate)
      ];
    });
    symbolBody.appendChild(createTable(headers, rows));
  }
  symbolCard.querySelector('.card-body')?.remove();
  symbolCard.appendChild(symbolBody);
  
  // Per-Strategy P&L Card
  const strategyCard = createCard('P&L by Strategy');
  const strategyBody = document.createElement('div');
  strategyBody.className = 'card-body';
  
  if (!analytics || !analytics.pnl_per_strategy || Object.keys(analytics.pnl_per_strategy).length === 0) {
    strategyBody.innerHTML = '<p class="text-muted text-sm text-center">No strategy data yet</p>';
  } else {
    const headers = ['Strategy', 'Realized P&L', 'Unrealized P&L', 'Total P&L', 'Trades', 'Win Rate'];
    const rows = Object.entries(analytics.pnl_per_strategy).map(([strategy, data]) => {
      const winRate = data.trades > 0 ? (data.wins / data.trades) * 100 : 0;
      return [
        strategy,
        coloredPnL(data.realized_pnl || 0),
        coloredPnL(data.unrealized_pnl || 0),
        coloredPnL(data.total_pnl || 0),
        data.trades || 0,
        formatPercent(winRate)
      ];
    });
    strategyBody.appendChild(createTable(headers, rows));
  }
  strategyCard.querySelector('.card-body')?.remove();
  strategyCard.appendChild(strategyBody);
  
  fullWidthContainer.appendChild(symbolCard);
  fullWidthContainer.appendChild(strategyCard);
  container.appendChild(fullWidthContainer);
  
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
 * Logs Tab - Engine logs with auto-scroll follow mode and severity filter
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
  
  // Add filter handler
  levelSelect.addEventListener('change', () => {
    filterAndDisplayLogs(state.logs, levelSelect.value);
  });
  
  const followLabel = document.createElement('label');
  followLabel.style.display = 'flex';
  followLabel.style.alignItems = 'center';
  followLabel.style.gap = 'var(--space-2)';
  followLabel.style.cursor = 'pointer';
  followLabel.innerHTML = `
    <input type="checkbox" id="log-follow" checked style="cursor: pointer;">
    <span class="text-sm">Follow logs</span>
  `;
  
  toolbar.appendChild(levelSelect);
  toolbar.appendChild(followLabel);
  
  // Logs display
  const logsBody = document.createElement('div');
  logsBody.className = 'card-body';
  logsBody.id = 'logs-container';
  logsBody.style.maxHeight = '600px';
  logsBody.style.overflowY = 'auto';
  logsBody.style.position = 'relative';
  
  const logsPre = document.createElement('pre');
  logsPre.id = 'logs-display';
  logsPre.className = 'font-mono text-sm';
  logsPre.style.whiteSpace = 'pre-wrap';
  logsPre.style.margin = '0';
  logsPre.style.wordBreak = 'break-word';
  
  if (state.logs.length === 0) {
    logsPre.textContent = 'No logs available';
  } else {
    logsPre.textContent = state.logs
      .map(log => formatLogEntry(log))
      .join('\n');
  }
  
  logsBody.appendChild(logsPre);
  
  // Set up scroll detection for follow mode
  logsBody.addEventListener('scroll', () => {
    const followCheckbox = document.getElementById('log-follow');
    if (!followCheckbox) return;
    
    const isNearBottom = logsBody.scrollHeight - logsBody.scrollTop - logsBody.clientHeight < 50;
    
    // If user scrolls up, disable follow
    if (!isNearBottom && followCheckbox.checked) {
      followCheckbox.checked = false;
    }
    // If user scrolls to bottom, enable follow
    else if (isNearBottom && !followCheckbox.checked) {
      followCheckbox.checked = true;
    }
  });
  
  logsCard.querySelector('.card-body')?.remove();
  logsCard.appendChild(toolbar);
  logsCard.appendChild(logsBody);
  
  container.appendChild(logsCard);
  
  return container;
}

/**
 * Format a single log entry with timestamp
 */
function formatLogEntry(log) {
  const timestamp = formatTime(log.timestamp || log.ts);
  const level = (log.level || 'INFO').padEnd(7);
  const source = (log.logger || log.source || 'system').padEnd(20);
  return `${timestamp} [${level}] ${source}: ${log.message}`;
}

/**
 * Filter and display logs based on severity level
 */
function filterAndDisplayLogs(logs, filterLevel) {
  const logsPre = document.getElementById('logs-display');
  if (!logsPre) return;
  
  let filteredLogs = logs;
  if (filterLevel) {
    filteredLogs = logs.filter(log => 
      (log.level || '').toUpperCase() === filterLevel.toUpperCase()
    );
  }
  
  if (filteredLogs.length === 0) {
    logsPre.textContent = `No logs available for level: ${filterLevel || 'ALL'}`;
  } else {
    logsPre.textContent = filteredLogs
      .map(log => formatLogEntry(log))
      .join('\n');
  }
  
  // Auto-scroll if follow is enabled
  const followCheckbox = document.getElementById('log-follow');
  const logsContainer = document.getElementById('logs-container');
  if (followCheckbox?.checked && logsContainer) {
    logsContainer.scrollTop = logsContainer.scrollHeight;
  }
}
