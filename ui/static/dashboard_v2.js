// Dashboard V2 - Optimized with tab-based conditional loading and proper polling
// No infinite loops, proper cleanup, and optimized refresh intervals

let marketClockOffsetMs = null;
let clockTimerId = null;
const currencyFormatters = {};
const pollingTimers = {};
let currentActiveTab = 'overview';

/**
 * Fetch with retry logic for improved resilience
 */
async function fetchWithRetry(url, options = {}, retries = 3, delayMs = 1000) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) {
        return response;
      }
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, attempt)));
        continue;
      }
      return response;
    } catch (error) {
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, attempt)));
        continue;
      }
      throw error;
    }
  }
}

function formatInr(value, fractionDigits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const key = `inr-${fractionDigits}`;
  if (!currencyFormatters[key]) {
    currencyFormatters[key] = new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
  }
  return currencyFormatters[key].format(Number(value));
}

/**
 * Clear all polling timers for a specific category
 */
function clearPollingTimers(category) {
  if (pollingTimers[category]) {
    pollingTimers[category].forEach(timer => clearInterval(timer));
    pollingTimers[category] = [];
  }
}

/**
 * Register a polling timer for cleanup
 */
function registerTimer(category, timer) {
  if (!pollingTimers[category]) {
    pollingTimers[category] = [];
  }
  pollingTimers[category].push(timer);
}

/**
 * Setup tab switching with proper polling management
 */
function setupTabs() {
  const tabs = document.querySelectorAll(".tabs .tab");
  const pages = document.querySelectorAll(".tab-page");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-tab");
      
      // Clean up previous tab's polling
      clearPollingTimers(currentActiveTab);
      
      // Update active state
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      pages.forEach((page) => {
        if (page.id === `tab-${target}`) {
          page.classList.add("active");
        } else {
          page.classList.remove("active");
        }
      });

      // Update current tab and start its polling
      currentActiveTab = target;
      startTabPolling(target);
    });
  });
}

/**
 * Start polling for specific tab
 */
function startTabPolling(tab) {
  switch(tab) {
    case 'overview':
      // Load initial data
      fetchPortfolioSummary();
      fetchRecentSignals();
      fetchOpenPositions();
      fetchRecentOrders();
      fetchEquityCurve();
      fetchTodaySummary();
      fetchStrategyStats();
      // Setup polling
      registerTimer('overview', setInterval(fetchPortfolioSummary, 15000));
      registerTimer('overview', setInterval(fetchRecentSignals, 10000));
      registerTimer('overview', setInterval(fetchOpenPositions, 15000));
      registerTimer('overview', setInterval(fetchRecentOrders, 15000));
      registerTimer('overview', setInterval(fetchTodaySummary, 30000));
      registerTimer('overview', setInterval(fetchStrategyStats, 30000));
      break;
      
    case 'signals':
      fetchRecentSignals();
      registerTimer('signals', setInterval(fetchRecentSignals, 5000));
      break;
      
    case 'orders':
      fetchRecentOrders();
      registerTimer('orders', setInterval(fetchRecentOrders, 5000));
      break;
      
    case 'logs':
      fetchRecentLogs();
      registerTimer('logs', setInterval(fetchRecentLogs, 5000));
      break;
      
    case 'monitor':
      refreshTradeFlow();
      registerTimer('monitor', setInterval(refreshTradeFlow, 5000));
      break;
      
    case 'analytics':
      refreshAnalytics();
      registerTimer('analytics', setInterval(refreshAnalytics, 30000));
      break;
      
    case 'trades':
      refreshTradesTable();
      registerTimer('trades', setInterval(refreshTradesTable, 10000));
      break;
      
    case 'config':
      fetchConfigSummary();
      // Config doesn't need polling
      break;
  }
}

// ===== Clock & Market Status =====

function startClockTicker() {
  if (clockTimerId) {
    return;
  }
  clockTimerId = setInterval(updateMarketClock, 1000);
}

function updateMarketClock() {
  if (marketClockOffsetMs == null) {
    return;
  }
  const clock = document.getElementById("market-clock");
  if (!clock) {
    return;
  }
  const now = new Date(Date.now() - marketClockOffsetMs);
  const hh = now.getHours().toString().padStart(2, "0");
  const mm = now.getMinutes().toString().padStart(2, "0");
  const ss = now.getSeconds().toString().padStart(2, "0");
  clock.textContent = `${hh}:${mm}:${ss} IST`;
}

async function refreshMeta() {
  try {
    const res = await fetchWithRetry("/api/meta");
    if (!res.ok) {
      console.warn("Failed to refresh meta:", res.status);
      return;
    }

    const data = await res.json();
    const badge = document.getElementById("market-status-badge");
    const clock = document.getElementById("market-clock");

    const isOpen = !!data.market_open;

    if (badge) {
      if (isOpen) {
        badge.textContent = "MARKET OPEN";
        badge.classList.remove("badge-closed");
        badge.classList.add("badge-open");
      } else {
        badge.textContent = "MARKET CLOSED";
        badge.classList.remove("badge-open");
        badge.classList.add("badge-closed");
      }
    }

    if (data.now_ist) {
      const serverTs = Date.parse(data.now_ist);
      if (!Number.isNaN(serverTs)) {
        marketClockOffsetMs = Date.now() - serverTs;
        updateMarketClock();
        startClockTicker();
      }
    }
  } catch (err) {
    console.error("Failed to refresh meta:", err);
  }
}

async function refreshServerTime() {
  try {
    const res = await fetchWithRetry("/api/system/time");
    if (!res.ok) {
      console.warn("Failed to refresh server time:", res.status);
      return;
    }
    const data = await res.json();
    const serverTimeEl = document.getElementById("server-time");
    if (serverTimeEl && data.utc) {
      const utcDate = new Date(data.utc);
      const istDate = new Date(utcDate.getTime() + (5.5 * 60 * 60 * 1000));
      const hh = istDate.getUTCHours().toString().padStart(2, "0");
      const mm = istDate.getUTCMinutes().toString().padStart(2, "0");
      const ss = istDate.getUTCSeconds().toString().padStart(2, "0");
      serverTimeEl.textContent = `${hh}:${mm}:${ss} IST`;
    }
  } catch (err) {
    console.error("Failed to refresh server time:", err);
  }
}

// ===== Engine Status =====

function formatAge(seconds) {
  if (seconds == null || Number.isNaN(seconds)) {
    return "unknown age";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s ago`;
  }
  if (seconds < 3600) {
    return `${(seconds / 60).toFixed(1)}m ago`;
  }
  return `${(seconds / 3600).toFixed(1)}h ago`;
}

function renderEngineStatus(status) {
  const badge = document.getElementById("engine-status-badge");
  const meta = document.getElementById("engines-meta");
  const pillBadge = document.getElementById("engine-status-pill");
  
  if (!badge || !meta) {
    return;
  }

  if (!status) {
    badge.textContent = "UNKNOWN";
    badge.className = "engine-badge badge badge-muted";
    meta.textContent = "Engine status unavailable.";
    if (pillBadge) {
      pillBadge.textContent = "Engines: UNKNOWN";
      pillBadge.className = "pill pill-muted";
    }
    return;
  }

  const running = Boolean(status.running);
  badge.textContent = running ? "RUNNING" : "STOPPED";
  badge.className = `engine-badge badge ${running ? "badge-success" : "badge-danger"}`;

  if (pillBadge) {
    pillBadge.textContent = running ? "Engines: RUNNING" : "Engines: STOPPED";
    pillBadge.className = `pill ${running ? "pill-ok" : "pill-warn"}`;
  }

  const ageSeconds = typeof status.checkpoint_age_seconds === "number" ? status.checkpoint_age_seconds : null;
  const checkpointTs = status.last_checkpoint_ts ? new Date(status.last_checkpoint_ts) : null;
  const checkpointLabel = checkpointTs && !Number.isNaN(checkpointTs.valueOf())
    ? checkpointTs.toLocaleString()
    : "unknown";
  const ageLabel = formatAge(ageSeconds);
  const marketLabel = status.market_open ? "Market OPEN" : "Market CLOSED";
  const errorLabel = status.error ? ` • ${status.error}` : "";

  meta.textContent = `Last checkpoint: ${checkpointLabel} • Age: ${ageLabel} • ${marketLabel}${errorLabel}`;
}

async function refreshEngines() {
  try {
    const res = await fetchWithRetry("/api/engines/status");
    if (!res.ok) {
      console.warn("Failed to refresh engines:", res.status);
      return;
    }
    const data = await res.json();
    const status = Array.isArray(data.engines) ? data.engines[0] : null;
    renderEngineStatus(status);
  } catch (err) {
    console.error("Failed to refresh engines:", err);
  }
}

// ===== Portfolio =====

function fmtMoney(value) {
  return formatInr(value, 2);
}

function setSignedValue(el, value) {
  if (!el) return;
  el.classList.remove("positive", "negative");
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    el.textContent = "—";
    return;
  }
  const num = Number(value);
  el.textContent = fmtMoney(num);
  if (num > 0) el.classList.add("positive");
  if (num < 0) el.classList.add("negative");
}

async function fetchPortfolioSummary() {
  try {
    const res = await fetchWithRetry("/api/portfolio/summary");
    if (!res.ok) {
      console.warn(`Failed to fetch portfolio summary: HTTP ${res.status}`);
      return;
    }
    const summary = await res.json();

    const elEquity = document.getElementById("pf-equity");
    if (!elEquity) return;
    
    const elReal = document.getElementById("pf-realized");
    const elUnreal = document.getElementById("pf-unrealized");
    const elDaily = document.getElementById("pf-daily");
    const elExposure = document.getElementById("pf-exposure");
    const elFree = document.getElementById("pf-free");
    const elPos = document.getElementById("pf-positions");

    elEquity.textContent = fmtMoney(summary.equity);
    setSignedValue(elReal, summary.total_realized_pnl);
    setSignedValue(elUnreal, summary.total_unrealized_pnl);
    setSignedValue(elDaily, summary.daily_pnl);

    if (summary.exposure_pct === null || summary.exposure_pct === undefined) {
      if (elExposure) {
        elExposure.textContent = "—";
        elExposure.classList.remove("positive", "negative");
      }
    } else if (elExposure) {
      const pctValue = Number(summary.exposure_pct) * 100;
      const pctText = `${pctValue.toFixed(1)}%`;
      elExposure.textContent = pctText;
      elExposure.classList.remove("positive", "negative");
      if (pctValue <= 50) elExposure.classList.add("positive");
      if (pctValue >= 90) elExposure.classList.add("negative");
    }

    if (elFree) {
      elFree.textContent = fmtMoney(summary.free_notional);
      elFree.classList.remove("positive", "negative");
    }

    if (elPos) {
      const count = summary.position_count ?? 0;
      elPos.textContent = summary.has_positions ? `Positions: ${count}` : "Positions: none";
    }
  } catch (err) {
    console.error("Failed to fetch portfolio summary:", err);
  }
}

// ===== Signals =====

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function fetchRecentSignals() {
  try {
    const res = await fetchWithRetry("/api/signals/recent");
    if (!res.ok) {
      console.warn("Failed to fetch recent signals:", res.status);
      return;
    }
    const data = await res.json();
    const signals = data.signals || [];

    const countBadge = document.getElementById("signals-count");
    if (countBadge) {
      countBadge.textContent = signals.length;
    }

    const tbody = document.getElementById("signals-body");
    if (!tbody) return;

    if (signals.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted small">No signals yet.</td></tr>';
      return;
    }

    tbody.innerHTML = signals.slice(0, 20).map(sig => {
      const signalClass = (sig.signal || '').toLowerCase() === 'buy' ? 'signal-buy' : 
                         (sig.signal || '').toLowerCase() === 'sell' ? 'signal-sell' : '';
      return `
        <tr>
          <td>${escapeHtml(sig.time || sig.timestamp || '')}</td>
          <td>${escapeHtml(sig.symbol || '')}</td>
          <td>${escapeHtml(sig.tf || sig.timeframe || '')}</td>
          <td class="${signalClass}">${escapeHtml(sig.signal || '')}</td>
          <td>${sig.price != null ? formatInr(sig.price, 2) : '—'}</td>
          <td>${escapeHtml(sig.strategy || sig.reason || '')}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Failed to fetch recent signals:", err);
  }
}

// ===== Positions & Orders =====

async function fetchOpenPositions() {
  try {
    const res = await fetchWithRetry("/api/positions/open");
    if (!res.ok) {
      console.warn("Failed to fetch positions:", res.status);
      return;
    }
    const data = await res.json();
    const positions = data.positions || [];

    const countBadge = document.getElementById("positions-count");
    if (countBadge) {
      countBadge.textContent = positions.length;
    }

    const tbody = document.getElementById("positions-body");
    if (!tbody) return;

    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-muted small">No open positions.</td></tr>';
      return;
    }

    tbody.innerHTML = positions.slice(0, 10).map(pos => {
      const sideClass = (pos.side || '').toLowerCase() === 'long' ? 'side-buy' : 'side-sell';
      const pnl = parseFloat(pos.unrealized_pnl || pos.pnl || 0);
      const pnlClass = pnl > 0 ? 'text-profit' : pnl < 0 ? 'text-loss' : '';
      return `
        <tr>
          <td>${escapeHtml(pos.symbol || '')}</td>
          <td class="${sideClass}">${escapeHtml((pos.side || '').toUpperCase())}</td>
          <td>${pos.quantity || pos.qty || 0}</td>
          <td>${formatInr(pos.average_price || pos.avg_price || 0)}</td>
          <td class="${pnlClass}">${formatInr(pnl)}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Failed to fetch positions:", err);
  }
}

async function fetchRecentOrders() {
  try {
    const res = await fetchWithRetry("/api/orders/recent");
    if (!res.ok) {
      console.warn("Failed to fetch orders:", res.status);
      return;
    }
    const data = await res.json();
    const orders = data.orders || [];

    const countBadge = document.getElementById("orders-count");
    if (countBadge) {
      countBadge.textContent = orders.length;
    }

    const tbody = document.getElementById("orders-body");
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted small">No recent orders.</td></tr>';
      return;
    }

    tbody.innerHTML = orders.slice(0, 10).map(order => {
      const side = (order.side || '').toUpperCase();
      const sideClass = side === 'BUY' ? 'side-buy' : side === 'SELL' ? 'side-sell' : '';
      const statusClass = (order.status || '').toLowerCase() === 'complete' ? 'badge-success' :
                         (order.status || '').toLowerCase() === 'rejected' ? 'badge-danger' : 'badge-muted';
      return `
        <tr>
          <td>${escapeHtml(order.timestamp || order.ts || '')}</td>
          <td>${escapeHtml(order.symbol || '')}</td>
          <td class="${sideClass}">${side}</td>
          <td>${order.quantity || order.qty || 0}</td>
          <td>${formatInr(order.price || order.avg_price || 0)}</td>
          <td><span class="badge ${statusClass}">${escapeHtml(order.status || '')}</span></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Failed to fetch orders:", err);
  }
}

// ===== Today's Summary =====

async function fetchTodaySummary() {
  try {
    const res = await fetchWithRetry("/api/summary/today");
    if (!res.ok) {
      console.warn("Failed to fetch today summary:", res.status);
      return;
    }
    const data = await res.json();

    const elRealizedPnl = document.getElementById("today-realized-pnl");
    if (elRealizedPnl) {
      const pnl = parseFloat(data.realized_pnl || 0);
      elRealizedPnl.textContent = formatInr(pnl);
      elRealizedPnl.classList.remove('positive', 'negative', 'flat');
      if (pnl > 0) elRealizedPnl.classList.add('positive');
      else if (pnl < 0) elRealizedPnl.classList.add('negative');
      else elRealizedPnl.classList.add('flat');
    }

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };

    setText('today-num-trades', data.num_trades || 0);
    setText('today-win-rate', `${((data.win_rate || 0) * 100).toFixed(1)}%`);
    setText('today-win-trades', data.win_trades || 0);
    setText('today-loss-trades', data.loss_trades || 0);
    setText('today-largest-win', formatInr(data.largest_win || 0));
    setText('today-largest-loss', formatInr(data.largest_loss || 0));
    setText('today-avg-r', (data.avg_r || 0).toFixed(2));
  } catch (err) {
    console.error("Failed to fetch today summary:", err);
  }
}

// ===== Strategy Stats =====

async function fetchStrategyStats() {
  try {
    const res = await fetchWithRetry("/api/stats/strategies");
    if (!res.ok) {
      console.warn("Failed to fetch strategy stats:", res.status);
      return;
    }
    const data = await res.json();
    const strategies = data.strategies || [];

    const tbody = document.getElementById("strategy-stats-body");
    if (!tbody) return;

    if (strategies.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-muted small">No strategy data.</td></tr>';
      return;
    }

    tbody.innerHTML = strategies.map(strat => {
      const pnl = parseFloat(strat.total_pnl || 0);
      const pnlClass = pnl > 0 ? 'text-profit' : pnl < 0 ? 'text-loss' : '';
      return `
        <tr>
          <td>${escapeHtml(strat.strategy || '')}</td>
          <td>${strat.signals || 0}</td>
          <td>${strat.trades || 0}</td>
          <td class="${pnlClass}">${formatInr(pnl)}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Failed to fetch strategy stats:", err);
  }
}

// ===== Equity Curve =====

async function fetchEquityCurve() {
  try {
    const res = await fetchWithRetry("/api/stats/equity");
    if (!res.ok) {
      console.warn("Failed to fetch equity curve:", res.status);
      return;
    }
    const data = await res.json();
    const curve = data.curve || [];

    const countBadge = document.getElementById("equity-points-count");
    if (countBadge) {
      countBadge.textContent = `${curve.length} pts`;
    }

    const svg = document.getElementById("equity-chart");
    if (!svg || curve.length === 0) return;

    renderEquityCurve(svg, curve);
  } catch (err) {
    console.error("Failed to fetch equity curve:", err);
  }
}

function renderEquityCurve(svg, curve) {
  if (curve.length < 2) {
    svg.innerHTML = '<text x="50" y="20" fill="#94a3b8" font-size="10">Insufficient data</text>';
    return;
  }

  const equities = curve.map(p => parseFloat(p.equity || 0));
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const range = maxEquity - minEquity;
  const padding = range * 0.1 || 1000;
  const yMin = minEquity - padding;
  const yMax = maxEquity + padding;

  const width = 800;
  const height = 300;
  const margin = { top: 20, right: 40, bottom: 30, left: 60 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;

  const xScale = (i) => margin.left + (i / (curve.length - 1 || 1)) * chartWidth;
  const yScale = (val) => margin.top + chartHeight - ((val - yMin) / (yMax - yMin)) * chartHeight;

  let pathData = "";
  curve.forEach((point, i) => {
    const x = xScale(i);
    const y = yScale(parseFloat(point.equity || 0));
    pathData += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
  });

  svg.innerHTML = "";

  // Grid lines
  const numGridLines = 5;
  for (let i = 0; i <= numGridLines; i++) {
    const y = margin.top + (i / numGridLines) * chartHeight;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", margin.left);
    line.setAttribute("x2", width - margin.right);
    line.setAttribute("y1", y);
    line.setAttribute("y2", y);
    line.setAttribute("stroke", "rgba(148, 163, 184, 0.2)");
    line.setAttribute("stroke-width", "1");
    svg.appendChild(line);

    const value = yMax - (i / numGridLines) * (yMax - yMin);
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", margin.left - 10);
    text.setAttribute("y", y + 4);
    text.setAttribute("text-anchor", "end");
    text.setAttribute("fill", "#94a3b8");
    text.setAttribute("font-size", "10");
    text.textContent = formatInr(value, 0);
    svg.appendChild(text);
  }

  // Equity curve path
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", pathData);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#22c55e");
  path.setAttribute("stroke-width", "2");
  svg.appendChild(path);
}

// ===== Logs =====

async function fetchRecentLogs() {
  try {
    const res = await fetchWithRetry("/api/logs/recent?limit=50");
    if (!res.ok) {
      console.warn("Failed to fetch logs:", res.status);
      return;
    }
    const data = await res.json();
    const logs = data.logs || [];

    const container = document.getElementById("logs-content");
    if (!container) return;

    if (logs.length === 0) {
      container.innerHTML = '<div class="log-empty">No recent logs.</div>';
      return;
    }

    container.innerHTML = logs.map(log => {
      const levelClass = `log-${(log.level || 'info').toLowerCase()}`;
      return `<div class="log-line ${levelClass}">[${log.timestamp || ''}] [${log.level || 'INFO'}] ${escapeHtml(log.message || '')}</div>`;
    }).join('');
  } catch (err) {
    console.error("Failed to fetch logs:", err);
  }
}

// ===== Config =====

async function fetchConfigSummary() {
  try {
    const res = await fetchWithRetry("/api/config/summary");
    if (!res.ok) {
      console.warn("Failed to fetch config:", res.status);
      return;
    }
    const data = await res.json();

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value || '—';
    };

    setText('config-path', data.config_path || '');
    setText('config-universe', (data.fno_universe || []).join(', ') || '—');
    setText('config-capital', formatInr(data.paper_capital || 0));
    setText('config-risk-per-trade', formatInr(data.risk_per_trade || 0));
    setText('config-max-daily-loss', formatInr(data.max_daily_loss || 0));
    setText('config-max-exposure', data.max_exposure ? `${(data.max_exposure * 100).toFixed(0)}%` : '—');
    setText('config-risk-profile', data.risk_profile || '—');
    setText('config-meta-enabled', data.meta_enabled ? 'Enabled' : 'Disabled');

    const modePill = document.getElementById('config-mode-pill');
    if (modePill) {
      const mode = (data.mode || 'paper').toLowerCase();
      modePill.textContent = mode.toUpperCase();
      modePill.className = `config-pill config-pill-${mode}`;
    }
  } catch (err) {
    console.error("Failed to fetch config:", err);
  }
}

// ===== Health =====

async function fetchHealth() {
  try {
    const res = await fetchWithRetry("/api/health");
    if (!res.ok) {
      console.warn("Failed to fetch health:", res.status);
      return;
    }
    const data = await res.json();
    
    // Update health indicators if elements exist
    const healthBadge = document.getElementById("health-status");
    if (healthBadge) {
      const isHealthy = data.errors === 0 || (data.errors || 0) < 5;
      healthBadge.textContent = isHealthy ? "HEALTHY" : "WARNINGS";
      healthBadge.className = `badge ${isHealthy ? "badge-success" : "badge-warn"}`;
    }

    const errorCount = document.getElementById("health-errors");
    if (errorCount) {
      errorCount.textContent = data.errors || 0;
    }
  } catch (err) {
    console.error("Failed to fetch health:", err);
  }
}

// ===== Trade Flow Monitor =====

async function refreshTradeFlow() {
  try {
    const res = await fetchWithRetry("/api/monitor/trade_flow");
    if (!res.ok) {
      console.warn("Failed to fetch trade flow:", res.status);
      return;
    }
    const data = await res.json();

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value || 0;
    };

    setText('flow-signals-seen', data.signals_seen || 0);
    setText('flow-evaluated', data.evaluated || 0);
    setText('flow-allowed', data.allowed || 0);
    setText('flow-vetoed', data.vetoed || 0);
    setText('flow-orders-placed', data.orders_placed || 0);
    setText('flow-orders-filled', data.orders_filled || 0);
  } catch (err) {
    console.error("Failed to fetch trade flow:", err);
  }
}

// ===== Analytics Tab =====

async function refreshAnalytics() {
  try {
    const res = await fetchWithRetry("/api/analytics/summary");
    if (!res.ok) {
      console.warn("Failed to fetch analytics:", res.status);
      return;
    }
    const data = await res.json();
    
    // Update analytics displays if needed
    console.log("Analytics data:", data);
  } catch (err) {
    console.error("Failed to fetch analytics:", err);
  }
}

// ===== Trades Tab =====

async function refreshTradesTable() {
  try {
    const res = await fetchWithRetry("/api/orders/recent?limit=50");
    if (!res.ok) {
      console.warn("Failed to fetch trades:", res.status);
      return;
    }
    const data = await res.json();
    const orders = data.orders || [];

    const tbody = document.getElementById("trades-table-body");
    if (!tbody) return;

    if (orders.length === 0) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-muted small">No trades today.</td></tr>';
      return;
    }

    tbody.innerHTML = orders.map(order => {
      const side = (order.side || '').toUpperCase();
      const sideClass = side === 'BUY' ? 'side-buy' : side === 'SELL' ? 'side-sell' : '';
      const pnl = parseFloat(order.pnl || order.realized_pnl || 0);
      const pnlClass = pnl > 0 ? 'text-profit' : pnl < 0 ? 'text-loss' : '';

      return `
        <tr>
          <td>${escapeHtml(order.timestamp || order.ts || '')}</td>
          <td>${escapeHtml(order.symbol || '')}</td>
          <td class="${sideClass}">${side}</td>
          <td>${formatInr(order.entry_price || order.avg_price || 0)}</td>
          <td>${formatInr(order.exit_price || order.price || 0)}</td>
          <td>${order.quantity || order.qty || 0}</td>
          <td class="${pnlClass}">${formatInr(pnl)}</td>
          <td>${(order.r_multiple || order.r || 0).toFixed(2)}</td>
          <td>${escapeHtml(order.strategy || '')}</td>
          <td><span class="badge badge-muted">${escapeHtml(order.status || '')}</span></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("Failed to refresh trades table:", err);
  }
}

// ===== Logs Tabs Setup =====

function setupLogsTabs() {
  const logTabs = document.querySelectorAll('.logs-tabs .log-tab');
  logTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      logTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const kind = tab.dataset.kind;
      fetchRecentLogs(kind);
    });
  });
}

// ===== Initialization =====

function initDashboard() {
  // Setup tab switching
  setupTabs();
  setupLogsTabs();

  // Start global polling (always-on components)
  refreshMeta();
  setInterval(refreshMeta, 10000);
  
  refreshServerTime();
  setInterval(refreshServerTime, 10000);
  
  refreshEngines();
  setInterval(refreshEngines, 10000);
  
  fetchHealth();
  setInterval(fetchHealth, 30000);

  // Start polling for the initial tab (overview)
  startTabPolling('overview');

  console.log('Dashboard V2 initialized - tab-based polling active');
}

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", initDashboard);

// Export for external access
window.refreshLogs = fetchRecentLogs;
window.refreshTradeFlow = refreshTradeFlow;
window.refreshAnalytics = refreshAnalytics;
window.refreshTradesTable = refreshTradesTable;
