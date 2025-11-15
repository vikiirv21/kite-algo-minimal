// Simple tab switching + meta refresh.
// You can later plug in your existing /api/state polling in the TODO section.

let marketClockOffsetMs = null;
let clockTimerId = null;
const currencyFormatters = {};

/**
 * Fetch with retry logic for improved resilience
 * @param {string} url - The URL to fetch
 * @param {object} options - Fetch options
 * @param {number} retries - Number of retries (default: 3)
 * @param {number} delayMs - Initial delay between retries in ms (default: 1000)
 * @returns {Promise<Response>}
 */
async function fetchWithRetry(url, options = {}, retries = 3, delayMs = 1000) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (response.ok) {
        return response;
      }
      // If not ok but not last attempt, retry
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, attempt)));
        continue;
      }
      return response; // Return last failed response
    } catch (error) {
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, attempt)));
        continue;
      }
      throw error; // Throw on last attempt
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

function setupTabs() {
  const tabs = document.querySelectorAll(".tabs .tab");
  const pages = document.querySelectorAll(".tab-page");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.getAttribute("data-tab");

      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      pages.forEach((page) => {
        if (page.id === `tab-${target}`) {
          page.classList.add("active");
        } else {
          page.classList.remove("active");
        }
      });
    });
  });
}

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

    if (isOpen) {
      badge.textContent = "MARKET OPEN";
      badge.classList.remove("badge-closed");
      badge.classList.add("badge-open");
    } else {
      badge.textContent = "MARKET CLOSED";
      badge.classList.remove("badge-open");
      badge.classList.add("badge-closed");
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
  if (!badge || !meta) {
    return;
  }

  if (!status) {
    badge.textContent = "UNKNOWN";
    badge.className = "engine-badge badge badge-muted";
    meta.textContent = "Engine status unavailable.";
    return;
  }

  const running = Boolean(status.running);
  badge.textContent = running ? "RUNNING" : "STOPPED";
  badge.className = `engine-badge badge ${running ? "badge-success" : "badge-danger"}`;

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
      throw new Error(`HTTP ${res.status}`);
    }
    const summary = await res.json();

    const elEquity = document.getElementById("pf-equity");
    if (!elEquity) {
      return;
    }
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
    const elEquity = document.getElementById("pf-equity");
    if (elEquity) {
      elEquity.textContent = "Error loading data";
      elEquity.classList.remove("positive", "negative");
    }
  }
}

function renderSignalsTable(signals) {
  const tbody = document.getElementById("signals-body");
  const countEl = document.getElementById("signals-count");
  if (!tbody) {
    return;
  }

  tbody.innerHTML = "";

  if (!Array.isArray(signals) || signals.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "text-muted small";
    cell.textContent = "No signals yet.";
    row.appendChild(cell);
    tbody.appendChild(row);
    if (countEl) {
      countEl.textContent = "0";
    }
    return;
  }

  if (countEl) {
    countEl.textContent = String(signals.length);
  }

  signals
    .slice()
    .reverse()
    .forEach((signal) => {
      const tr = document.createElement("tr");

      const ts = signal.ts || signal.timestamp || "";
      const timeDisplay = ts ? ts.replace("T", " ").slice(0, 19) : "—";

      const tdTime = document.createElement("td");
      tdTime.textContent = timeDisplay;
      tr.appendChild(tdTime);

      const tdSymbol = document.createElement("td");
      tdSymbol.textContent = signal.symbol || signal.logical || "—";
      tr.appendChild(tdSymbol);

      const tdTf = document.createElement("td");
      tdTf.textContent = signal.tf || "";
      tr.appendChild(tdTf);

      const tdSignal = document.createElement("td");
      const sigText = (signal.signal || "").toUpperCase() || "—";
      const badge = document.createElement("span");
      badge.classList.add("signal-tag");
      if (sigText === "BUY") badge.classList.add("signal-buy");
      else if (sigText === "SELL") badge.classList.add("signal-sell");
      else if (sigText === "HOLD") badge.classList.add("signal-hold");
      else badge.classList.add("signal-other");
      badge.textContent = sigText;
      tdSignal.appendChild(badge);
      tr.appendChild(tdSignal);

      const tdPrice = document.createElement("td");
      const price = signal.price;
      if (price === null || price === undefined || Number.isNaN(Number(price))) {
        tdPrice.textContent = "—";
      } else {
        tdPrice.textContent = Number(price).toFixed(2);
      }
      tr.appendChild(tdPrice);

      const tdStrategy = document.createElement("td");
      tdStrategy.textContent = signal.strategy || signal.profile || "";
      tr.appendChild(tdStrategy);

      tbody.appendChild(tr);
    });

  renderSignalsDetailTable(signals);
}

function renderSignalsDetailTable(signals) {
  const table = document.getElementById("table-all-signals");
  if (!table) {
    return;
  }
  if (!Array.isArray(signals) || signals.length === 0) {
    table.innerHTML = `
      <tr>
        <td colspan="8" class="text-muted small">No strategy signals yet.</td>
      </tr>
    `;
    return;
  }
  const rows = signals
    .slice()
    .reverse()
    .map((s) => {
      const ts = s.ts || s.timestamp || "";
      const timeDisplay = ts ? ts.replace("T", " ").slice(0, 19) : "—";
      const sigText = (s.signal || "").toUpperCase();
      return `
        <tr>
          <td>${timeDisplay}</td>
          <td>${s.symbol || s.logical || "—"}</td>
          <td>${s.tf || s.timeframe || ""}</td>
          <td>${sigText}</td>
          <td>${s.price != null ? Number(s.price).toFixed(2) : "—"}</td>
          <td>${s.profile || ""}</td>
          <td>${s.confidence || ""}</td>
          <td>${s.reason || ""}</td>
        </tr>
      `;
    })
    .join("");
  table.innerHTML = rows;
}

async function fetchRecentSignals() {
  try {
    const res = await fetchWithRetry("/api/signals/recent?limit=50");
    if (!res.ok) {
      console.warn(`Failed to fetch signals: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderSignalsTable(data);
  } catch (err) {
    console.error("Failed to fetch recent signals:", err);
    // Render empty state on error
    renderSignalsTable([]);
  }
}

function formatTimestamp(ts) {
  if (!ts) {
    return "—";
  }
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) {
    return ts.replace("T", " ").slice(0, 19);
  }
  return date.toLocaleString("en-IN", { hour12: false });
}

function renderHealthSummary(payload) {
  const pill = document.getElementById("health-market-pill");
  if (pill) {
    const status = (payload.market_status?.status || "").toUpperCase();
    pill.classList.remove("pill-open", "pill-closed", "pill-preopen");
    let label = "Market Closed";
    let cls = "pill-closed";
    if (status === "OPEN") {
      label = "Market Open";
      cls = "pill-open";
    } else if (status === "PRE_OPEN") {
      label = "Pre-Open";
      cls = "pill-preopen";
    }
    pill.textContent = label;
    pill.classList.add(cls);
  }

  const logHealth = payload.log_health || {};
  const lastLogEl = document.getElementById("health-last-log");
  if (lastLogEl) {
    lastLogEl.textContent = formatTimestamp(logHealth.last_log_ts);
  }
  const lastErrEl = document.getElementById("health-last-error");
  if (lastErrEl) {
    lastErrEl.textContent = logHealth.last_error_ts
      ? formatTimestamp(logHealth.last_error_ts)
      : "No recent errors";
  }
  const errCountEl = document.getElementById("health-error-count");
  if (errCountEl) {
    errCountEl.textContent = logHealth.error_count_recent ?? 0;
  }
  const warnCountEl = document.getElementById("health-warning-count");
  if (warnCountEl) {
    warnCountEl.textContent = logHealth.warning_count_recent ?? 0;
  }
}

function renderLogsPanel(data) {
  const pre = document.getElementById("logs-body");
  const countEl = document.getElementById("logs-count");
  const tabPre = document.getElementById("logs-stream");
  if (!pre) {
    return;
  }

  // Extract entries from response
  const entries = data.logs || data.entries || data || [];

  if (!Array.isArray(entries) || entries.length === 0) {
    const emptyMsg = "No logs available.";
    pre.textContent = emptyMsg;
    if (tabPre) tabPre.textContent = emptyMsg;
    if (countEl) countEl.textContent = "0";
    return;
  }

  const lines = entries.map((entry) => {
    const ts = formatTimestamp(entry.ts);
    const level = (entry.level || "").toUpperCase() || "INFO";
    const loggerName = entry.logger ? `${entry.logger} - ` : "";
    return `[${level}] ${ts} ${loggerName}${entry.message || ""}`.trim();
  });
  pre.textContent = lines.join("\n");
  if (tabPre) {
    tabPre.textContent = lines.join("\n");
    tabPre.scrollTop = tabPre.scrollHeight;
  }
  if (countEl) {
    countEl.textContent = String(entries.length);
  }
}

async function fetchHealth() {
  try {
    const res = await fetchWithRetry("/api/health");
    if (!res.ok) {
      console.warn(`Failed to fetch health: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderHealthSummary(data);
  } catch (err) {
    console.error("Failed to fetch system health:", err);
  }
}

async function fetchRecentLogs(kind = null) {
  try {
    let url = "/api/logs/recent?limit=120";
    if (kind) {
      url += `&kind=${encodeURIComponent(kind)}`;
    }
    const res = await fetchWithRetry(url);
    if (!res.ok) {
      console.warn(`Failed to fetch logs: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderLogsPanel(data);
  } catch (err) {
    console.error("Failed to fetch recent logs:", err);
    // Show error in logs panel
    const pre = document.getElementById("logs-body");
    const tabPre = document.getElementById("logs-stream");
    if (pre) pre.textContent = `Error loading logs: ${err.message}`;
    if (tabPre) tabPre.textContent = `Error loading logs: ${err.message}`;
  }
}

function setupLogsTabs() {
  const logsTabs = document.querySelectorAll(".logs-tab");
  let currentLogsKind = null;
  let logsRefreshInterval = null;

  logsTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const kind = tab.getAttribute("data-log-kind") || null;
      currentLogsKind = kind;

      // Update active tab
      logsTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      // Fetch logs for this kind
      fetchRecentLogs(kind);

      // Clear and restart the refresh interval
      if (logsRefreshInterval) {
        clearInterval(logsRefreshInterval);
      }
      logsRefreshInterval = setInterval(() => fetchRecentLogs(kind), 15000);
    });
  });
}

function renderOpenPositions(positions) {
  const tbody = document.getElementById("positions-body");
  const detailTable = document.getElementById("table-positions-detailed");
  const countEl = document.getElementById("positions-count");
  if (!tbody) {
    return;
  }

  const renderPlaceholder = (target, cols) => {
    target.innerHTML = `
      <tr>
        <td colspan="${cols}" class="text-muted small">No open positions.</td>
      </tr>
    `;
  };

  tbody.innerHTML = "";

  if (!Array.isArray(positions) || positions.length === 0) {
    renderPlaceholder(tbody, 5);
    if (detailTable) {
      renderPlaceholder(detailTable, 6);
    }
    if (countEl) {
      countEl.textContent = "0";
    }
    return;
  }

  if (countEl) {
    countEl.textContent = String(positions.length);
  }

  const rowsOverview = [];
  const rowsDetailed = [];

  positions.forEach((pos) => {
    const unreal = pos.unrealized_pnl != null ? Number(pos.unrealized_pnl) : 0;
    rowsOverview.push(`
      <tr>
        <td>${pos.symbol || "—"}</td>
        <td>${pos.side || "FLAT"}</td>
        <td>${pos.quantity ?? "0"}</td>
        <td>${pos.avg_price != null ? Number(pos.avg_price).toFixed(2) : "—"}</td>
        <td class="${unreal > 0 ? "text-profit" : unreal < 0 ? "text-loss" : ""}">${unreal.toFixed(2)}</td>
      </tr>
    `);

    const lastValue =
      pos.last_price != null
        ? Number(pos.last_price).toFixed(2)
        : pos.avg_price != null
        ? Number(pos.avg_price).toFixed(2)
        : "—";
    rowsDetailed.push(`
      <tr>
        <td>${pos.symbol || "—"}</td>
        <td>${pos.side || ""}</td>
        <td>${pos.quantity ?? "0"}</td>
        <td>${pos.avg_price != null ? Number(pos.avg_price).toFixed(2) : "—"}</td>
        <td>${lastValue}</td>
        <td class="${unreal > 0 ? "text-profit" : unreal < 0 ? "text-loss" : ""}">${unreal.toFixed(2)}</td>
      </tr>
    `);
  });

  tbody.innerHTML = rowsOverview.join("");
  if (detailTable) {
    detailTable.innerHTML = rowsDetailed.join("");
  }
}

function renderRecentOrders(orders) {
  const tbody = document.getElementById("orders-body");
  const countEl = document.getElementById("orders-count");
  const detailTable = document.getElementById("table-recent-orders");
  if (!tbody) {
    return;
  }

  const renderPlaceholder = (target, cols) => {
    target.innerHTML = `
      <tr>
        <td colspan="${cols}" class="text-muted small">No orders yet.</td>
      </tr>
    `;
  };

  tbody.innerHTML = "";

  if (!Array.isArray(orders) || orders.length === 0) {
    renderPlaceholder(tbody, 6);
    if (detailTable) {
      renderPlaceholder(detailTable, 6);
    }
    if (countEl) {
      countEl.textContent = "0";
    }
    return;
  }

  if (countEl) {
    countEl.textContent = String(orders.length);
  }

  const rows = orders
    .slice()
    .reverse()
    .map((order) => {
      const ts = order.ts || "";
      const timeDisplay = ts ? ts.replace("T", " ").slice(0, 19) : "—";
      return `
        <tr>
          <td>${timeDisplay}</td>
          <td>${order.symbol || "—"}</td>
          <td>${order.side || ""}</td>
          <td>${order.quantity ?? "0"}</td>
          <td>${order.price != null ? Number(order.price).toFixed(2) : "—"}</td>
          <td>${order.status || ""}</td>
        </tr>
      `;
    })
    .join("");

  tbody.innerHTML = rows;
  if (detailTable) {
    detailTable.innerHTML = rows;
  }
}

async function fetchOpenPositions() {
  try {
    const res = await fetchWithRetry("/api/positions/open");
    if (!res.ok) {
      console.warn(`Failed to fetch positions: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    renderOpenPositions(data);
  } catch (err) {
    console.error("Failed to fetch open positions:", err);
    renderOpenPositions([]);
  }
}

async function fetchRecentOrders() {
  try {
    const res = await fetchWithRetry("/api/orders/recent?limit=50");
    if (!res.ok) {
      console.warn(`Failed to fetch orders: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    const orders = data.orders || data || [];
    renderRecentOrders(orders);
  } catch (err) {
    console.error("Failed to fetch recent orders:", err);
    renderRecentOrders([]);
  }
}

async function fetchStrategyStats() {
  try {
    const res = await fetchWithRetry("/api/stats/strategies?days=1");
    if (!res.ok) {
      console.warn(`Failed to fetch strategy stats: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    const tbody = document.getElementById("strategy-tbody");
    const countEl = document.getElementById("strategy-count");
    if (!tbody) {
      return;
    }

    if (!Array.isArray(data) || data.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-muted small">No strategy signals yet.</td>
        </tr>
      `;
      if (countEl) {
        countEl.textContent = "0";
      }
      return;
    }

    const rows = data.map((row) => {
      const logical = row.logical || row.key || "";
      const symbol = row.symbol || "";
      const tf = row.timeframe || "";
      const lastSignal = (row.last_signal || "").toUpperCase();
      const lastPrice =
        row.last_price != null ? Number(row.last_price).toFixed(2) : "–";
      const buyCount = row.buy_count ?? 0;
      const sellCount = row.sell_count ?? 0;
      const exitCount = row.exit_count ?? 0;
      const holdCount = row.hold_count ?? 0;

      let pillClass = "signal-hold";
      if (lastSignal === "BUY") pillClass = "signal-buy";
      else if (lastSignal === "SELL") pillClass = "signal-sell";
      else if (lastSignal === "EXIT") pillClass = "signal-exit";

      return `
        <tr>
          <td>${logical}</td>
          <td>${symbol}</td>
          <td>${tf}</td>
          <td><span class="signal-pill ${pillClass}">${lastSignal || "–"}</span></td>
          <td>${lastPrice}</td>
          <td>${buyCount} / ${sellCount} / ${exitCount} / ${holdCount}</td>
        </tr>
      `;
    });

    tbody.innerHTML = rows.join("");
    if (countEl) {
      countEl.textContent = String(data.length);
    }
  } catch (err) {
    console.error("Failed to fetch strategy stats:", err);
    const tbody = document.getElementById("strategy-tbody");
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-muted small">Error loading strategy stats.</td>
        </tr>
      `;
    }
  }
}

async function fetchEquityCurve() {
  try {
    const res = await fetchWithRetry("/api/stats/equity?days=1");
    if (!res.ok) {
      console.warn(`Failed to fetch equity curve: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    const svg = document.getElementById("equity-chart");
    const countEl = document.getElementById("equity-points-count");
    if (!svg) {
      return;
    }

    if (!Array.isArray(data) || data.length === 0) {
      svg.innerHTML = `
        <text x="50" y="22" text-anchor="middle" fill="#9ca3af" font-size="4">
          No equity snapshots yet.
        </text>`;
      if (countEl) {
        countEl.textContent = "0 pts";
      }
      return;
    }

    const equities = data.map((d) => Number(d.equity || 0));
    const capitals = data.map((d) => Number(d.paper_capital || 0));
    const realizeds = data.map((d) => Number(d.realized || 0));
    const combined = equities.concat(capitals);
    const minY = Math.min(...combined);
    const maxY = Math.max(...combined);
    const spanY = maxY - minY || 1;
    const n = data.length;
    const stepX = n > 1 ? 100 / (n - 1) : 0;

    function makePath(values) {
      return values
        .map((value, idx) => {
          const x = idx * stepX;
          const norm = (value - minY) / spanY;
          const y = 40 - norm * 30 - 5;
          return `${idx === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
        })
        .join(" ");
    }

    const pathCapital = makePath(capitals);
    const pathEquity = makePath(equities);
    const pathRealized = makePath(realizeds);

    svg.innerHTML = `
      <path d="${pathCapital}" fill="none" stroke="#3b82f6" stroke-width="0.7" stroke-opacity="0.8" />
      <path d="${pathEquity}" fill="none" stroke="#22c55e" stroke-width="0.9" stroke-opacity="0.9" />
      <path d="${pathRealized}" fill="none" stroke="#f97316" stroke-width="0.7" stroke-opacity="0.9" stroke-dasharray="2 2" />
    `;

    if (countEl) {
      countEl.textContent = `${data.length} pts`;
    }
  } catch (err) {
    console.error("Failed to fetch equity curve:", err);
    const svg = document.getElementById("equity-chart");
    if (svg) {
      svg.innerHTML = `
        <text x="50" y="22" text-anchor="middle" fill="#ef4444" font-size="4">
          Error loading equity curve.
        </text>`;
    }
  }
}

async function fetchConfigSummary() {
  try {
    const res = await fetchWithRetry("/api/config/summary");
    if (!res.ok) {
      console.warn(`Failed to fetch config summary: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();

    const mode = (data.mode || "").toLowerCase();
    const cfgPath = data.config_path || "";
    const universe = Array.isArray(data.fno_universe)
      ? data.fno_universe.join(", ")
      : String(data.fno_universe || "");
    const capital = Number(data.paper_capital || 0);
    const riskPerTrade = Number(data.risk_per_trade_pct || 0);
    const maxDailyLoss = Number(data.max_daily_loss || 0);
    const maxExposure = Number(data.max_exposure_pct || 0);
    const riskProfile = data.risk_profile || "Default";
    const metaEnabled = Boolean(data.meta_enabled);

    const elPath = document.getElementById("config-path");
    if (elPath) {
      const trimmed = cfgPath.replace(/.*kite-algo-minimal[\\/]/, "");
      elPath.textContent = trimmed || cfgPath || "—";
    }
    const elUniverse = document.getElementById("config-universe");
    if (elUniverse) {
      elUniverse.textContent = universe || "—";
    }
    const elCap = document.getElementById("config-capital");
    if (elCap) {
      elCap.textContent = capital
        ? capital.toLocaleString("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
          })
        : "—";
    }
    const elRpt = document.getElementById("config-risk-per-trade");
    if (elRpt) {
      elRpt.textContent = `${(riskPerTrade * 100).toFixed(2)} %`;
    }
    const elDaily = document.getElementById("config-max-daily-loss");
    if (elDaily) {
      elDaily.textContent = maxDailyLoss
        ? maxDailyLoss.toLocaleString("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
          })
        : "—";
    }
    const elExposure = document.getElementById("config-max-exposure");
    if (elExposure) {
      elExposure.textContent = `${maxExposure.toFixed(2)}x`;
    }
    const elProfile = document.getElementById("config-risk-profile");
    if (elProfile) {
      elProfile.textContent = riskProfile;
      elProfile.dataset.profile = riskProfile;
    }
    const elMeta = document.getElementById("config-meta-enabled");
    if (elMeta) {
      elMeta.textContent = metaEnabled ? "Enabled" : "Disabled";
      elMeta.style.color = metaEnabled ? "#22c55e" : "#9ca3af";
    }
    const elMode = document.getElementById("config-mode-pill");
    if (elMode) {
      const modeUpper = mode ? mode.toUpperCase() : "UNKNOWN";
      elMode.textContent = modeUpper;
      elMode.classList.remove("config-pill-paper", "config-pill-live", "config-pill-replay");
      if (mode === "paper") {
        elMode.classList.add("config-pill-paper");
      } else if (mode === "live") {
        elMode.classList.add("config-pill-live");
      } else if (mode === "replay") {
        elMode.classList.add("config-pill-replay");
      }
    }
  } catch (err) {
    console.error("Failed to fetch config summary:", err);
    // Set error message in config card
    const elPath = document.getElementById("config-path");
    if (elPath) {
      elPath.textContent = "Error loading config";
    }
  }
}

async function fetchTodaySummary() {
  try {
    const res = await fetchWithRetry("/api/summary/today");
    if (!res.ok) {
      console.warn(`Failed to fetch today summary: HTTP ${res.status}`);
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    const realized = Number(data.realized_pnl || 0);
    const numTrades = Number(data.num_trades || 0);
    const winTrades = Number(data.win_trades || 0);
    const lossTrades = Number(data.loss_trades || 0);
    const winRate = Number(data.win_rate || 0);
    const largestWin = Number(data.largest_win || 0);
    const largestLoss = Number(data.largest_loss || 0);
    const avgR = Number(data.avg_r || 0);

    const elDate = document.getElementById("today-date-label");
    if (elDate) {
      elDate.textContent = data.date || "Today";
    }

    const elPnl = document.getElementById("today-realized-pnl");
    if (elPnl) {
      elPnl.classList.remove("positive", "negative", "flat");
      elPnl.textContent = formatInr(realized, 0);
      if (realized > 0) elPnl.classList.add("positive");
      else if (realized < 0) elPnl.classList.add("negative");
      else elPnl.classList.add("flat");
    }

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };

    setText("today-num-trades", numTrades.toString());
    setText("today-win-trades", winTrades.toString());
    setText("today-loss-trades", lossTrades.toString());
    setText("today-win-rate", `${winRate.toFixed(1)} %`);

    setText("today-largest-win", formatInr(largestWin, 0));
    setText("today-largest-loss", formatInr(largestLoss, 0));
    setText("today-avg-r", avgR.toFixed(2));
  } catch (err) {
    console.error("Failed to fetch today summary:", err);
    const elPnl = document.getElementById("today-realized-pnl");
    if (elPnl) {
      elPnl.textContent = "Error";
      elPnl.classList.remove("positive", "negative", "flat");
    }
  }
}

// TODO: Plug your existing /api/state / SSE here
async function refreshState() {
  try {
    const res = await fetchWithRetry("/api/state");
    if (!res.ok) {
      console.warn(`Failed to refresh state: HTTP ${res.status}`);
      return;
    }

    const data = await res.json();

    // Example mapping; adjust field names to your actual JSON:
    // P&L
    if (data.paper_state && data.paper_state.meta) {
      const meta = data.paper_state.meta;
      const realized = meta.total_realized_pnl || 0;
      const unrealized = meta.total_unrealized_pnl || 0;
      const equity = meta.equity || 0;
      const realizedEl = document.getElementById("pnl-realized");
      const unrealEl = document.getElementById("pnl-unrealized");
      const equityEl = document.getElementById("pnl-equity");
      if (realizedEl) realizedEl.textContent = formatInr(realized, 0);
      if (unrealEl) unrealEl.textContent = formatInr(unrealized, 0);
      if (equityEl) equityEl.textContent = formatInr(equity, 0);
    }

    // Engine status (example booleans)
    if (data.engines) {
      const paperOk = data.engines.paper_ok ?? true;
      const liveOk = data.engines.live_ok ?? false;
      const scannerOk = data.engines.scanner_ok ?? true;

      const statusPaper = document.getElementById("status-paper");
      const statusLive = document.getElementById("status-live");
      const statusScanner = document.getElementById("status-scanner");
      if (statusPaper) statusPaper.classList.toggle("err", !paperOk);
      if (statusLive) statusLive.classList.toggle("err", !liveOk);
      if (statusScanner) statusScanner.classList.toggle("err", !scannerOk);
    }

    // Positions table (overview)
    const posBody = document.getElementById("table-open-positions");
    if (posBody && Array.isArray(data.positions)) {
      posBody.innerHTML = "";
      data.positions.slice(0, 20).forEach((p) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${p.symbol}</td>
          <td>${p.qty}</td>
          <td>${p.avg_price?.toFixed?.(2) ?? p.avg_price ?? "-"}</td>
          <td>${p.ltp?.toFixed?.(2) ?? p.ltp ?? "-"}</td>
          <td>${p.unrealized_pnl?.toFixed?.(0) ?? "-"}</td>
        `;
        posBody.appendChild(tr);
      });
    }

    // Recent signals (overview)
    const sigBody = document.getElementById("table-recent-signals");
    if (sigBody && Array.isArray(data.signals)) {
      sigBody.innerHTML = "";
      data.signals.slice(-30).reverse().forEach((s) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${s.time || ""}</td>
          <td>${s.symbol || ""}</td>
          <td>${s.tf || ""}</td>
          <td>${s.signal || ""}</td>
          <td>${s.price != null ? s.price.toFixed?.(2) ?? s.price : "-"}</td>
          <td>${s.reason || ""}</td>
        `;
        sigBody.appendChild(tr);
      });
    }

    // TODO: map to:
    // - table-all-signals
    // - table-positions-detailed
    // - table-recent-orders
    // using the data shape you already have
  } catch (err) {
    console.error("Failed to refresh state:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupLogsTabs();
  refreshMeta();
  setInterval(refreshMeta, 5000);
  refreshEngines();
  setInterval(refreshEngines, 5000);
  fetchPortfolioSummary();
  setInterval(fetchPortfolioSummary, 7000);
  fetchRecentSignals();
  setInterval(fetchRecentSignals, 8000);
  fetchOpenPositions();
  fetchRecentOrders();
  setInterval(fetchOpenPositions, 9000);
  setInterval(fetchRecentOrders, 9000);
  fetchHealth();
  fetchRecentLogs();
  fetchStrategyStats();
  fetchEquityCurve();
  fetchConfigSummary();
  fetchTodaySummary();
  setInterval(fetchHealth, 15000);
  setInterval(fetchRecentLogs, 15000);
  setInterval(fetchStrategyStats, 15000);
  setInterval(fetchEquityCurve, 20000);
  setInterval(fetchConfigSummary, 30000);
  setInterval(fetchTodaySummary, 30000);

  // Backtests tab initialization
  fetchBacktestRuns();

  // state polling every 3s (tune as you like)
  refreshState();
  setInterval(refreshState, 3000);
});

// ===== Backtests Tab =====

let currentBacktestRunId = null;

async function fetchBacktestRuns() {
  try {
    const res = await fetchWithRetry("/api/backtests");
    if (!res.ok) {
      console.warn("Failed to fetch backtest runs:", res.status);
      return;
    }

    const data = await res.json();
    const runs = data.runs || [];

    const countBadge = document.getElementById("backtests-count");
    if (countBadge) {
      countBadge.textContent = runs.length;
    }

    const listContainer = document.getElementById("backtests-list");
    if (!listContainer) return;

    if (runs.length === 0) {
      listContainer.innerHTML = `
        <div class="backtests-empty-state">
          <p>No backtests found.</p>
          <p class="text-muted small">Run <code>scripts/run_backtest.py</code> to generate one.</p>
        </div>
      `;
      return;
    }

    listContainer.innerHTML = "";

    runs.forEach((run) => {
      const item = document.createElement("div");
      item.className = "backtest-run-item";
      item.dataset.runId = `${run.strategy}/${run.run_id}`;

      const pnl = parseFloat(run.net_pnl || 0);
      const pnlClass = pnl > 0 ? "positive" : pnl < 0 ? "negative" : "neutral";
      const pnlText = formatInr(pnl, 0);

      const winRate = parseFloat(run.win_rate || 0).toFixed(1);
      const totalTrades = parseInt(run.total_trades || 0);

      // Format date range
      const dateFrom = run.date_from ? run.date_from.split("T")[0] : "N/A";
      const dateTo = run.date_to ? run.date_to.split("T")[0] : "N/A";

      item.innerHTML = `
        <div class="backtest-run-header">
          <span class="backtest-run-strategy">${escapeHtml(run.strategy)}</span>
          <span class="backtest-run-pnl ${pnlClass}">${pnlText}</span>
        </div>
        <div class="backtest-run-meta">
          <div class="backtest-run-meta-item">
            <span>Symbol:</span>
            <span>${escapeHtml(run.symbol)}</span>
          </div>
          <div class="backtest-run-meta-item">
            <span>TF:</span>
            <span>${escapeHtml(run.timeframe || "N/A")}</span>
          </div>
          <div class="backtest-run-meta-item">
            <span>Trades:</span>
            <span>${totalTrades}</span>
          </div>
          <div class="backtest-run-meta-item">
            <span>Win%:</span>
            <span>${winRate}%</span>
          </div>
          <div class="backtest-run-meta-item">
            <span>Period:</span>
            <span>${dateFrom}</span>
          </div>
          <div class="backtest-run-meta-item">
            <span>to:</span>
            <span>${dateTo}</span>
          </div>
        </div>
      `;

      item.addEventListener("click", () => {
        selectBacktestRun(item.dataset.runId);
      });

      listContainer.appendChild(item);
    });
  } catch (err) {
    console.error("Error fetching backtest runs:", err);
    const listContainer = document.getElementById("backtests-list");
    if (listContainer) {
      listContainer.innerHTML = `
        <div class="backtests-empty-state">
          <p>Error loading backtests.</p>
          <p class="text-muted small">${err.message}</p>
        </div>
      `;
    }
  }
}

function selectBacktestRun(runId) {
  currentBacktestRunId = runId;

  // Update selected state
  document.querySelectorAll(".backtest-run-item").forEach((item) => {
    if (item.dataset.runId === runId) {
      item.classList.add("selected");
    } else {
      item.classList.remove("selected");
    }
  });

  // Show loading state
  const emptyState = document.getElementById("backtests-detail-empty");
  const contentState = document.getElementById("backtests-detail-content");

  if (emptyState) emptyState.style.display = "none";
  if (contentState) contentState.style.display = "block";

  // Fetch details
  fetchBacktestDetails(runId);
  fetchBacktestEquityCurve(runId);
}

async function fetchBacktestDetails(runId) {
  try {
    const res = await fetchWithRetry(`/api/backtests/${encodeURIComponent(runId)}/summary`);
    if (!res.ok) {
      console.warn("Failed to fetch backtest details:", res.status);
      return;
    }

    const data = await res.json();
    const summary = data.summary || {};
    const summaryData = summary.summary || {};
    const config = summary.config || {};

    // Update title
    const titleEl = document.getElementById("backtest-detail-title");
    if (titleEl) {
      titleEl.textContent = `Backtest: ${summary.strategy || "Unknown"}`;
    }

    // Update badge
    const badgeEl = document.getElementById("backtest-detail-badge");
    if (badgeEl) {
      const pnl = parseFloat(summaryData.total_pnl || 0);
      badgeEl.textContent = pnl > 0 ? "Profitable" : pnl < 0 ? "Loss" : "Break Even";
      badgeEl.className = "badge " + (pnl > 0 ? "badge-open" : pnl < 0 ? "badge-closed" : "badge-muted");
    }

    // Update header details
    setText("backtest-strategy", summary.strategy || "N/A");
    setText("backtest-symbol", Array.isArray(config.symbols) ? config.symbols.join(", ") : config.symbols || "N/A");
    setText("backtest-timeframe", config.timeframe || "N/A");
    setText("backtest-date-range", `${config.from || "N/A"} to ${config.to || "N/A"}`);
    setText("backtest-capital", formatInr(config.capital || 0, 0));
    setText("backtest-run-id", runId);

    // Update metrics
    const netPnl = parseFloat(summaryData.total_pnl || 0);
    const totalTrades = parseInt(summaryData.total_trades || 0);
    const winRate = parseFloat(summaryData.win_rate || 0);
    const wins = parseInt(summaryData.wins || 0);
    const losses = parseInt(summaryData.losses || 0);
    const maxDd = parseFloat(summaryData.max_drawdown_pct || 0);

    setTextWithClass("backtest-net-pnl", formatInr(netPnl, 2), netPnl > 0 ? "positive" : netPnl < 0 ? "negative" : "");
    setText("backtest-total-trades", totalTrades);
    setText("backtest-win-rate", `${winRate.toFixed(1)}%`);
    setText("backtest-wins-losses", `${wins} / ${losses}`);
    setText("backtest-max-dd", `${maxDd.toFixed(2)}%`);

    // Calculate profit factor if available
    const grossProfit = parseFloat(summaryData.gross_profit || 0);
    const grossLoss = Math.abs(parseFloat(summaryData.gross_loss || 0));
    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : "—";
    setText("backtest-profit-factor", profitFactor);
  } catch (err) {
    console.error("Error fetching backtest details:", err);
    const titleEl = document.getElementById("backtest-detail-title");
    if (titleEl) {
      titleEl.textContent = "Error loading details";
    }
  }
}

async function fetchBacktestEquityCurve(runId) {
  try {
    const res = await fetchWithRetry(`/api/backtests/${encodeURIComponent(runId)}/equity_curve`);
    if (!res.ok) {
      console.warn("Failed to fetch equity curve:", res.status);
      return;
    }

    const data = await res.json();
    const curve = data.equity_curve || [];

    const pointsEl = document.getElementById("equity-curve-points");
    if (pointsEl) {
      pointsEl.textContent = `${curve.length} pts`;
    }

    renderEquityCurve(curve);
  } catch (err) {
    console.error("Error fetching equity curve:", err);
    const svg = document.getElementById("backtest-equity-chart");
    if (svg) {
      svg.innerHTML = `
        <text x="400" y="150" text-anchor="middle" fill="#ef4444" font-size="14">
          Error loading equity curve
        </text>
      `;
    }
  }
}

function renderEquityCurve(curve) {
  const svg = document.getElementById("backtest-equity-chart");
  if (!svg || curve.length === 0) {
    if (svg) {
      svg.innerHTML = `
        <text x="400" y="150" text-anchor="middle" fill="#94a3b8" font-size="14">
          No equity curve data available
        </text>
      `;
    }
    return;
  }

  // Extract equity values
  const equities = curve.map((p) => parseFloat(p.equity || 0));
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);

  // Add padding
  const range = maxEquity - minEquity;
  const padding = range * 0.1 || 1000;
  const yMin = minEquity - padding;
  const yMax = maxEquity + padding;

  const width = 800;
  const height = 300;
  const margin = { top: 20, right: 40, bottom: 30, left: 60 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;

  // Scale functions
  const xScale = (i) => margin.left + (i / (curve.length - 1 || 1)) * chartWidth;
  const yScale = (val) => margin.top + chartHeight - ((val - yMin) / (yMax - yMin)) * chartHeight;

  // Build path
  let pathData = "";
  curve.forEach((point, i) => {
    const x = xScale(i);
    const y = yScale(parseFloat(point.equity || 0));
    pathData += i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`;
  });

  // Clear and render
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

    // Y-axis label
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

  // Starting equity line
  const startEquity = equities[0];
  const startY = yScale(startEquity);
  const startLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  startLine.setAttribute("x1", margin.left);
  startLine.setAttribute("x2", width - margin.right);
  startLine.setAttribute("y1", startY);
  startLine.setAttribute("y2", startY);
  startLine.setAttribute("stroke", "#6366f1");
  startLine.setAttribute("stroke-width", "1");
  startLine.setAttribute("stroke-dasharray", "4");
  svg.appendChild(startLine);

  // Title
  const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
  title.setAttribute("x", width / 2);
  title.setAttribute("y", 15);
  title.setAttribute("text-anchor", "middle");
  title.setAttribute("fill", "#e5e7eb");
  title.setAttribute("font-size", "12");
  title.setAttribute("font-weight", "600");
  title.textContent = "Equity Over Time";
  svg.appendChild(title);
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setTextWithClass(id, value, className) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
    if (className) {
      el.className = "metric-value " + className;
    }
  }
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

