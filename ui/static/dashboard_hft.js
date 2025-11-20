// HFT Dashboard JavaScript
// Handles all API calls, polling, and UI updates

// ============================================================================
// Global State
// ============================================================================

let pollingIntervals = {};
let currentLogFilter = 'all';
let allLogs = [];

// ============================================================================
// Utility Functions
// ============================================================================

function formatINR(value) {
  if (value === null || value === undefined || isNaN(value)) return '₹0.00';
  const num = parseFloat(value);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num);
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || isNaN(value)) return '0.00';
  return parseFloat(value).toFixed(decimals);
}

function formatPercent(value) {
  if (value === null || value === undefined || isNaN(value)) return '0.0%';
  return formatNumber(value, 1) + '%';
}

function formatTime(isoString) {
  if (!isoString) return '--:--:--';
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-IN', { hour12: false });
  } catch (e) {
    return '--:--:--';
  }
}

function safeApiCall(url, fallback = {}) {
  return fetch(url)
    .then(res => res.ok ? res.json() : fallback)
    .catch(err => {
      console.warn(`API call failed: ${url}`, err);
      return fallback;
    });
}

// ============================================================================
// Tab Switching
// ============================================================================

function setupTabSwitching() {
  const tabs = document.querySelectorAll('.sidebar-tab');
  const sections = document.querySelectorAll('.section');
  
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const sectionName = tab.getAttribute('data-section');
      
      // Update active tab
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      
      // Update active section
      sections.forEach(s => s.classList.remove('active'));
      const targetSection = document.getElementById(`section-${sectionName}`);
      if (targetSection) {
        targetSection.classList.add('active');
      }
      
      // Load section-specific data
      loadSectionData(sectionName);
    });
  });
}

function loadSectionData(sectionName) {
  switch (sectionName) {
    case 'overview':
      updateOverview();
      break;
    case 'analytics':
      updateAnalytics();
      break;
    case 'positions':
      updatePositions();
      break;
    case 'strategies':
      updateStrategies();
      break;
    case 'signals':
      updateSignals();
      break;
    case 'risk':
      updateRisk();
      break;
    case 'logs':
      updateLogs();
      break;
  }
}

// ============================================================================
// Polling Management
// ============================================================================

function startPolling() {
  // Stop any existing polling
  stopPolling();
  
  // Update navbar elements every 5s
  updateNavbar();
  pollingIntervals.navbar = setInterval(updateNavbar, 5000);
  
  // Update overview every 10s
  pollingIntervals.overview = setInterval(updateOverview, 10000);
  
  // Update active section based on current tab
  const activeTab = document.querySelector('.sidebar-tab.active');
  if (activeTab) {
    const sectionName = activeTab.getAttribute('data-section');
    loadSectionData(sectionName);
  }
}

function stopPolling() {
  Object.values(pollingIntervals).forEach(interval => clearInterval(interval));
  pollingIntervals = {};
}

// ============================================================================
// Navbar Updates
// ============================================================================

async function updateNavbar() {
  try {
    // Fetch meta and trading summary
    const [metaData, tradingData] = await Promise.all([
      safeApiCall('/api/meta', {}),
      safeApiCall('/api/trading/summary', {})
    ]);
    
    // Update IST time
    if (metaData.now_ist) {
      const time = formatTime(metaData.now_ist);
      document.getElementById('ist-time').textContent = time;
    }
    
    // Update market status badge
    const marketBadge = document.getElementById('market-status-badge');
    if (metaData.market_open) {
      marketBadge.textContent = 'MARKET OPEN';
      marketBadge.className = 'badge badge-green';
    } else {
      marketBadge.textContent = 'MARKET CLOSED';
      marketBadge.className = 'badge badge-gray';
    }
    
    // Update engine status badge
    const engineBadge = document.getElementById('engine-status-badge');
    if (tradingData.engine_running) {
      engineBadge.textContent = 'ENGINE RUNNING';
      engineBadge.className = 'badge badge-green';
    } else {
      engineBadge.textContent = 'ENGINE STOPPED';
      engineBadge.className = 'badge badge-red';
    }
    
    // Update mode badge
    const modeBadge = document.getElementById('mode-badge');
    const mode = (tradingData.mode || 'paper').toUpperCase();
    modeBadge.textContent = mode;
    modeBadge.className = mode === 'LIVE' ? 'badge badge-red' : 'badge badge-blue';
    
  } catch (error) {
    console.error('Error updating navbar:', error);
  }
}

// ============================================================================
// Overview Section
// ============================================================================

async function updateOverview() {
  try {
    const [analyticsData, positionsData, signalsData, metaData, tradingData] = await Promise.all([
      safeApiCall('/api/analytics/summary', {}),
      safeApiCall('/api/positions_normalized', { positions: [] }),
      safeApiCall('/api/signals', []),
      safeApiCall('/api/meta', {}),
      safeApiCall('/api/trading/summary', {})
    ]);
    
    // Update KPIs
    const equity = analyticsData.equity || {};
    const realizedPnl = equity.realized_pnl || 0;
    const unrealizedPnl = equity.unrealized_pnl || 0;
    const totalPnl = realizedPnl + unrealizedPnl;
    
    updateKPI('kpi-total-pnl', totalPnl);
    updateKPI('kpi-realized-pnl', realizedPnl);
    updateKPI('kpi-unrealized-pnl', unrealizedPnl);
    
    const positionsCount = positionsData.positions ? positionsData.positions.length : 0;
    document.getElementById('kpi-positions').textContent = positionsCount;
    
    // Update status card
    const marketStatus = metaData.market_open ? 'OPEN' : 'CLOSED';
    const engineStatus = tradingData.engine_running ? 'RUNNING' : 'STOPPED';
    const mode = (tradingData.mode || 'paper').toUpperCase();
    const equityValue = equity.current_equity || 0;
    
    document.getElementById('status-market').textContent = marketStatus;
    document.getElementById('status-engine').textContent = engineStatus;
    document.getElementById('status-mode').textContent = mode;
    document.getElementById('status-equity').textContent = formatINR(equityValue);
    
    // Update mini positions list
    updateMiniPositionsList(positionsData.positions || []);
    
    // Update mini signals list
    updateMiniSignalsList(signalsData);
    
    // Update equity curve (mini)
    updateEquityCurveMini();
    
  } catch (error) {
    console.error('Error updating overview:', error);
  }
}

function updateKPI(elementId, value) {
  const element = document.getElementById(elementId);
  if (!element) return;
  
  element.textContent = formatINR(value);
  element.classList.remove('positive', 'negative');
  
  if (value > 0) {
    element.classList.add('positive');
  } else if (value < 0) {
    element.classList.add('negative');
  }
}

function updateMiniPositionsList(positions) {
  const container = document.getElementById('positions-mini-list');
  if (!container) return;
  
  if (!positions || positions.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No open positions</div></div>';
    return;
  }
  
  const html = positions.slice(0, 5).map(pos => {
    const symbol = pos.symbol || '';
    const qty = pos.quantity || 0;
    const unrealizedPnl = pos.unrealized_pnl || 0;
    const pnlClass = unrealizedPnl >= 0 ? 'text-success' : 'text-danger';
    
    return `
      <div class="mini-list-item">
        <div style="display: flex; justify-content: space-between;">
          <span>${symbol} (${qty})</span>
          <span class="${pnlClass}">${formatINR(unrealizedPnl)}</span>
        </div>
      </div>
    `;
  }).join('');
  
  container.innerHTML = html;
}

function updateMiniSignalsList(signals) {
  const container = document.getElementById('signals-mini-list');
  if (!container) return;
  
  if (!signals || signals.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No recent signals</div></div>';
    return;
  }
  
  const signalArray = Array.isArray(signals) ? signals : [];
  const html = signalArray.slice(-5).reverse().map(sig => {
    const symbol = sig.symbol || '';
    const signal = sig.signal || '';
    const ts = sig.ts || sig.timestamp || '';
    const time = ts ? new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '';
    
    return `
      <div class="mini-list-item">
        <div style="display: flex; justify-content: space-between;">
          <span>${symbol} - ${signal}</span>
          <span class="text-muted">${time}</span>
        </div>
      </div>
    `;
  }).join('');
  
  container.innerHTML = html;
}

async function updateEquityCurveMini() {
  try {
    const data = await safeApiCall('/api/analytics/equity_curve', { data: [] });
    const curveData = data.data || [];
    
    const canvas = document.getElementById('equity-curve-mini');
    if (!canvas || curveData.length === 0) return;
    
    drawEquityCurve(canvas, curveData);
  } catch (error) {
    console.error('Error updating equity curve:', error);
  }
}

// ============================================================================
// Analytics Section
// ============================================================================

async function updateAnalytics() {
  try {
    const analyticsData = await safeApiCall('/api/analytics/summary', {});
    
    // Update per-symbol table
    updatePnLTable('pnl-per-symbol-table', analyticsData.per_symbol || {}, 'Symbol');
    
    // Update per-strategy table
    updatePnLTable('pnl-per-strategy-table', analyticsData.per_strategy || {}, 'Strategy');
    
    // Update full equity curve
    updateEquityCurveFull();
    
  } catch (error) {
    console.error('Error updating analytics:', error);
  }
}

function updatePnLTable(containerId, data, labelColumn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  const entries = Object.entries(data);
  
  if (entries.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No data available</div></div>';
    return;
  }
  
  const rows = entries.map(([key, value]) => {
    const pnl = typeof value === 'number' ? value : (value.net_pnl || value.pnl || 0);
    const pnlClass = pnl >= 0 ? 'positive' : 'negative';
    
    return `
      <tr>
        <td>${key}</td>
        <td class="${pnlClass}">${formatINR(pnl)}</td>
      </tr>
    `;
  }).join('');
  
  container.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>${labelColumn}</th>
          <th>P&L</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function updateEquityCurveFull() {
  try {
    const data = await safeApiCall('/api/analytics/equity_curve', { data: [] });
    const curveData = data.data || [];
    
    const canvas = document.getElementById('equity-curve-full');
    if (!canvas || curveData.length === 0) return;
    
    drawEquityCurve(canvas, curveData);
  } catch (error) {
    console.error('Error updating full equity curve:', error);
  }
}

// ============================================================================
// Positions Section
// ============================================================================

async function updatePositions() {
  try {
    const data = await safeApiCall('/api/positions_normalized', { positions: [] });
    const positions = data.positions || [];
    
    const container = document.getElementById('positions-table');
    if (!container) return;
    
    if (positions.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No open positions</div></div>';
      return;
    }
    
    const rows = positions.map(pos => {
      const symbol = pos.symbol || '';
      const side = pos.quantity > 0 ? 'LONG' : 'SHORT';
      const qty = Math.abs(pos.quantity || 0);
      const avgPrice = pos.avg_price || 0;
      const lastPrice = pos.last_price || 0;
      const unrealizedPnl = pos.unrealized_pnl || 0;
      const realizedPnl = pos.realized_pnl || 0;
      const strategyId = pos.strategy_id || pos.info?.strategy_id || '-';
      
      const unrealizedClass = unrealizedPnl >= 0 ? 'positive' : 'negative';
      const realizedClass = realizedPnl >= 0 ? 'positive' : 'negative';
      
      return `
        <tr>
          <td>${symbol}</td>
          <td>${side}</td>
          <td>${qty}</td>
          <td>${formatNumber(avgPrice)}</td>
          <td>${formatNumber(lastPrice)}</td>
          <td class="${unrealizedClass}">${formatINR(unrealizedPnl)}</td>
          <td class="${realizedClass}">${formatINR(realizedPnl)}</td>
          <td>${strategyId}</td>
        </tr>
      `;
    }).join('');
    
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Qty</th>
            <th>Avg Price</th>
            <th>Last Price</th>
            <th>Unrealized P&L</th>
            <th>Realized P&L</th>
            <th>Strategy</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    
  } catch (error) {
    console.error('Error updating positions:', error);
  }
}

// ============================================================================
// Strategies Section
// ============================================================================

async function updateStrategies() {
  try {
    const strategies = await safeApiCall('/api/strategies', []);
    
    const container = document.getElementById('strategies-table');
    if (!container) return;
    
    if (!strategies || strategies.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No strategies configured</div></div>';
      return;
    }
    
    const rows = strategies.map(strat => {
      const id = strat.id || strat.strategy_code || '';
      const name = strat.name || id;
      const engine = strat.engine || strat.engine_type || '';
      const tags = Array.isArray(strat.tags) ? strat.tags.join(', ') : '';
      const enabled = strat.enabled ? 'Yes' : 'No';
      const enabledClass = strat.enabled ? 'text-success' : 'text-muted';
      const lastSignal = strat.last_signal_time || '-';
      const notes = strat.notes || '';
      
      return `
        <tr>
          <td>${name}</td>
          <td>${engine}</td>
          <td>${tags}</td>
          <td class="${enabledClass}">${enabled}</td>
          <td>${lastSignal}</td>
          <td>${notes}</td>
        </tr>
      `;
    }).join('');
    
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Engine</th>
            <th>Tags</th>
            <th>Enabled</th>
            <th>Last Signal</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    
  } catch (error) {
    console.error('Error updating strategies:', error);
  }
}

// ============================================================================
// Signals Section
// ============================================================================

async function updateSignals() {
  try {
    const signals = await safeApiCall('/api/signals', []);
    
    const container = document.getElementById('signals-table');
    if (!container) return;
    
    if (!signals || signals.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No signals available</div></div>';
      return;
    }
    
    const signalArray = Array.isArray(signals) ? signals : [];
    const rows = signalArray.slice().reverse().map(sig => {
      const ts = sig.ts || sig.timestamp || '';
      const time = ts ? new Date(ts).toLocaleTimeString('en-IN') : '';
      const symbol = sig.symbol || '';
      const side = sig.signal || sig.side || '';
      const price = sig.price || 0;
      const strategyId = sig.strategy || sig.strategy_id || '';
      const confidence = sig.confidence || '';
      
      return `
        <tr>
          <td>${time}</td>
          <td>${symbol}</td>
          <td>${side}</td>
          <td>${formatNumber(price)}</td>
          <td>${strategyId}</td>
          <td>${confidence}</td>
        </tr>
      `;
    }).join('');
    
    container.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Symbol</th>
            <th>Side</th>
            <th>Price</th>
            <th>Strategy</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    
  } catch (error) {
    console.error('Error updating signals:', error);
  }
}

// ============================================================================
// Risk Section
// ============================================================================

async function updateRisk() {
  try {
    const riskData = await safeApiCall('/api/risk/summary', {});
    
    // Update risk KPIs
    const maxLoss = riskData.max_daily_loss || 0;
    const usedLoss = riskData.used_loss || 0;
    const remainingLoss = riskData.remaining_loss || 0;
    const currentExposure = riskData.current_exposure_pct || 0;
    const maxExposure = riskData.max_exposure_pct || 0;
    const riskPerTrade = riskData.risk_per_trade_pct || 0;
    
    document.getElementById('risk-max-loss').textContent = formatINR(maxLoss);
    document.getElementById('risk-used-loss').textContent = formatINR(usedLoss);
    document.getElementById('risk-remaining-loss').textContent = formatINR(remainingLoss);
    document.getElementById('risk-exposure').textContent = `${formatPercent(currentExposure)} / ${formatPercent(maxExposure)}`;
    
    // Update risk bar
    const usedPercent = maxLoss > 0 ? Math.abs(usedLoss) / maxLoss * 100 : 0;
    document.getElementById('risk-bar-percent').textContent = formatPercent(usedPercent);
    document.getElementById('risk-bar-fill').style.width = `${Math.min(usedPercent, 100)}%`;
    
    // Update circuit breaker status
    const cbStatus = usedPercent >= 100 ? 'ACTIVE' : 'INACTIVE';
    const cbStatusElement = document.getElementById('circuit-breaker-status');
    cbStatusElement.textContent = cbStatus;
    cbStatusElement.className = usedPercent >= 100 ? 'status-value text-danger' : 'status-value text-success';
    
    document.getElementById('risk-per-trade').textContent = formatPercent(riskPerTrade * 100);
    
  } catch (error) {
    console.error('Error updating risk:', error);
  }
}

// ============================================================================
// Logs Section
// ============================================================================

async function updateLogs() {
  try {
    const logs = await safeApiCall('/api/logs/recent', { entries: [] });
    const logEntries = logs.entries || logs || [];
    
    allLogs = Array.isArray(logEntries) ? logEntries : [];
    renderLogs();
    
  } catch (error) {
    console.error('Error updating logs:', error);
  }
}

function renderLogs() {
  const container = document.getElementById('logs-container');
  if (!container) return;
  
  let filteredLogs = allLogs;
  
  // Apply filter
  if (currentLogFilter !== 'all') {
    filteredLogs = allLogs.filter(log => {
      const level = (log.level || '').toUpperCase();
      return level === currentLogFilter;
    });
  }
  
  if (filteredLogs.length === 0) {
    container.innerHTML = '<div class="empty-state"><div class="empty-state-message">No logs available</div></div>';
    return;
  }
  
  const html = filteredLogs.map(log => {
    const timestamp = log.timestamp || log.ts || '';
    const level = (log.level || 'INFO').toUpperCase();
    const message = log.message || '';
    
    return `
      <div class="log-entry">
        <span class="log-timestamp">${timestamp}</span>
        <span class="log-level ${level}">${level}</span>
        <span class="log-message">${message}</span>
      </div>
    `;
  }).join('');
  
  container.innerHTML = html;
}

function setupLogFilters() {
  const filterBtns = document.querySelectorAll('.log-filter-btn');
  
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const level = btn.getAttribute('data-level');
      currentLogFilter = level;
      
      // Update active button
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      // Re-render logs
      renderLogs();
    });
  });
}

// ============================================================================
// Chart Drawing (Simple Canvas Implementation)
// ============================================================================

function drawEquityCurve(canvas, data) {
  if (!canvas || !data || data.length === 0) return;
  
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  
  // Clear canvas
  ctx.clearRect(0, 0, width, height);
  
  // Extract equity values
  const equityValues = data.map(d => d.equity || 0);
  const minValue = Math.min(...equityValues);
  const maxValue = Math.max(...equityValues);
  const range = maxValue - minValue || 1;
  
  // Calculate points
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((d.equity - minValue) / range) * height;
    return { x, y };
  });
  
  // Draw line
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((point, i) => {
    if (i === 0) {
      ctx.moveTo(point.x, point.y);
    } else {
      ctx.lineTo(point.x, point.y);
    }
  });
  ctx.stroke();
  
  // Draw fill
  ctx.fillStyle = 'rgba(6, 182, 212, 0.1)';
  ctx.beginPath();
  ctx.moveTo(points[0].x, height);
  points.forEach(point => {
    ctx.lineTo(point.x, point.y);
  });
  ctx.lineTo(points[points.length - 1].x, height);
  ctx.closePath();
  ctx.fill();
}

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  console.log('HFT Dashboard initializing...');
  
  // Setup tab switching
  setupTabSwitching();
  
  // Setup log filters
  setupLogFilters();
  
  // Initial data load
  updateNavbar();
  updateOverview();
  
  // Start polling
  startPolling();
  
  console.log('HFT Dashboard initialized');
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  stopPolling();
});
